from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field, replace
from pathlib import Path

from loomwork import AGENTS_DIR, SOURCES_DIR
from loomwork.agents import AGENTS, Agent
from loomwork.declaration import Declaration
from loomwork.installation import Installation, Wiring, say, warn
from loomwork.registry import Registry


@dataclass(frozen=True)
class Loom:
    """What this machine can do with its rules source: the registry it remembers, and the namespace a caller insists on."""

    registry: Registry = field(default_factory=Registry)
    # one registry serves several accounts, so a caller that knows its namespace says so
    namespace: str | None = None
    agents_dir: Path = AGENTS_DIR

    @property
    def installation(self) -> Installation:
        """The source as something that can act: what a tool offered for this run, else what `point_at` remembered."""
        invoker = self.invoker()
        offered = invoker.offered_source() if invoker else None
        source = offered or self.registry.source
        namespace = self.namespace or self.registry.namespace or (invoker.names_source(offered) if offered else None)
        if not source or not namespace:
            raise SystemExit("no source yet — install the plugin, or run 'init <path-to-rules-repo>'")
        self.registry.remember_namespace(namespace)
        return Installation(
            namespace=namespace,
            agents_dir=self.agents_dir,
            source=source,
            former_namespaces=tuple(name for name in self.registry.namespaces if name != namespace),
        )

    @staticmethod
    def invoker() -> Agent | None:
        """The tool that invoked us, which says so by bringing the rules along — Claude's plugin does."""
        return next((agent for agent in AGENTS if agent.offered_source()), None)

    @staticmethod
    def present() -> tuple[Agent, ...]:
        return tuple(agent for agent in AGENTS if agent.present())

    def agents_for(self, project_dir: Path) -> tuple[Agent, ...]:
        """The tools this project asked for. An invoking tool is enough on its own — it is the one asking."""
        chosen = self.registry.agents_for(project_dir)
        if chosen:
            return tuple(agent for agent in AGENTS if agent.NAME in chosen)
        invoker = self.invoker()
        return (invoker,) if invoker else self.present()

    def point_at(self, source: Path) -> None:
        """Remember a rules repo and converge everything that follows from it."""
        if not (source / "AGENTS.md").is_file():
            raise SystemExit(f"{source} holds no AGENTS.md — is that the rules repo?")
        namespace = self.namespace or self.origin_owner(source)
        self.registry.remember_source(source, namespace)
        replace(self, namespace=namespace).installation.initialize(self.present())

    @staticmethod
    def origin_owner(source: Path) -> str:
        """How a cloned source names itself: the owner segment of its origin — Acme/agent-rules becomes acme."""
        origin = subprocess.run(
            ["git", "-C", str(source), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=False,
        )
        if origin.returncode != 0:
            raise SystemExit(f"{source} has no git origin to name a namespace after — pass --namespace")
        return re.split(r"[:/]+", origin.stdout.strip().rstrip("/").removesuffix(".git"))[-2].lower()

    def add(self, project: Path, chosen: tuple[str, ...]) -> None:
        """Take a project under management: fetch what it declares if this machine lacks it, then wire the chosen tools."""
        self.adopt_declared_source(project)
        self.registry.add(project, list(chosen))
        say(str(self.wire(self.installation, project)))

    def adopt_declared_source(self, project: Path) -> None:
        """A project names the rules it wants; a machine with none yet gets them from there, so `init` stays optional."""
        if self.invoker() or self.registry.source:
            return
        declaration = Declaration.read(project)
        if declaration is None:
            return
        self.registry.remember_source(self.fetch(declaration.source), declaration.namespace)

    @staticmethod
    def fetch(source: str) -> Path:
        """Clone a declared source into our own directory — ssh first, since a team's rules are usually private."""
        host, owner, repo = Declaration.segments(source)
        into = SOURCES_DIR / owner / repo
        if into.is_dir():
            return into
        into.parent.mkdir(parents=True, exist_ok=True)
        for url in (f"git@{host}:{owner}/{repo}.git", f"https://{host}/{owner}/{repo}.git"):
            say(f"fetching {url}")
            if subprocess.run(["git", "clone", "--quiet", url, str(into)], check=False).returncode == 0:
                return into
        raise SystemExit(f"could not clone {source} — clone it yourself and run 'init <path>'")

    def wire(self, installation: Installation, project: Path) -> Wiring:
        """Wire one project and let the registry follow: whoever triggered it, a wired project is a managed one."""
        wiring = installation.wire(project, self.agents_for(project))
        if wiring.declaration:
            self.registry.add(wiring.project_dir)
        else:
            self.registry.drop(wiring.project_dir)
        return wiring

    def remove(self, project: Path) -> None:
        self.installation.unwire_project(project, self.agents_for(project))
        if self.registry.drop(project):
            say(f"dropped {project}")
        else:
            warn(f"{project} was not registered — unwired it anyway")

    def sync(self, project: Path | None) -> None:
        """Refresh from the source: one project when named, otherwise every registered one."""
        installation = self.installation
        # `claude plugin update` refreshes the plugin copy, and it is no git checkout to pull
        if not self.invoker():
            installation.pull()
        if project:
            self.wire(installation, project)
            return
        for project_dir in self.registry.projects:
            if not project_dir.is_dir():
                warn(f"{project_dir} is gone — dropping it")
                self.registry.drop(project_dir)
                continue
            self.wire(installation, project_dir)

    def status(self) -> None:
        installation = self.installation
        say(f"source {installation.source} as '{installation.namespace}'")
        for project_dir in self.registry.projects:
            declaration = Declaration.read(project_dir) if project_dir.is_dir() else None
            wanted = ", ".join(declaration.rules) if declaration else f"no {Declaration.FILE_NAME}"
            say(f"  {project_dir} — {wanted}")
        if not self.registry.projects:
            say("  no projects yet — one gets recorded the first time it is wired")

    def uninstall(self) -> None:
        """Undo everything on this machine: every project, then the bridges and the registry."""
        installation = self.installation
        for project_dir in self.registry.projects:
            if project_dir.is_dir():
                installation.unwire_project(project_dir, self.agents_for(project_dir))
        installation.tear_down(self.present())
        self.registry.forget()
