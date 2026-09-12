from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from installer.agents import Agent


def say(message: str) -> None:
    print(f"agents-config: {message}")


def warn(message: str) -> None:
    print(f"agents-config: {message}", file=sys.stderr)


def rmdir_quiet(directory: Path) -> None:
    try:
        directory.rmdir()
    except OSError:
        pass


@dataclass(frozen=True)
class Installation:
    """The agent-agnostic substrate — agents dir, project containers, link primitives. Agents only bridge into it, never build it."""

    namespace: str
    # fixed at the .agents standard location — tools like OpenCode find it only there
    agents_dir: Path = Path("~/.agents").expanduser().resolve()
    repo_dir: Path = Path(__file__).resolve().parent.parent

    # a path component that also sits unquoted in the shell hook line — keep it boring
    NAMESPACE_RE: ClassVar[re.Pattern] = re.compile(r"[\w.-]+", re.ASCII)
    STACKS_RE: ClassVar[re.Pattern] = re.compile(r"^stacks:\s*\[(.*)\]\s*$")
    # three hops up from the container (.agents/rules/<namespace>/) is the project root; relative so the link survives project moves
    PROJECT_MD_TARGET: ClassVar[str] = "../../../AGENTS.md"
    # the wholesale rules-link shape agents lay beside their project config — namespace-free, so configs share it
    PROJECT_RULES_TARGET: ClassVar[str] = "../.agents/rules"
    # two hops up from .aiassistant/rules/ is that same project root
    ASSISTANT_MD_TARGET: ClassVar[str] = "../../AGENTS.md"
    PULL_TIMEOUT_SECONDS: ClassVar[int] = 8

    def install(self, agents: tuple[Agent, ...]) -> None:
        """Once per machine: register the hook on present agents and converge the machine — projects wire per session."""
        bridged = [agent for agent in agents if agent.present()]
        for agent in bridged:
            agent.register(self)
        if not self.pull():
            warn("could not pull — installing the clone as it stands")
        self.converge(agents)
        say(f"installed as '{self.namespace}' into {self.agents_dir}")
        if bridged:
            say(f"bridged {', '.join(type(agent).__name__ for agent in bridged)}")
        else:
            warn("no agent config dirs found — nothing bridged; rerun after an agent's first launch")

    def sync(self, project: str | None, agents: tuple[Agent, ...]) -> None:
        """What the hook runs at every session start: pull the repo, then link."""
        # stays silent on success — a session-start hook's stdout lands in the hosting agent's context
        self.pull()
        self.link(project, agents)

    def link(self, project: str | None, agents: tuple[Agent, ...]) -> Path:
        """Converge agents dir and bridges, then wire the given project — the session's cwd by default."""
        self.converge(agents)
        # the hook passes the session's project as the argument — wiring follows wherever sessions happen
        project_dir = Path(project).resolve() if project else Path.cwd()
        self.wire_project(project_dir, agents)
        return project_dir

    def converge(self, agents: tuple[Agent, ...]) -> None:
        """Populate the agents dir and lay every present agent's bridges."""
        self.populate_agents_dir()
        for agent in agents:
            if agent.present():
                agent.bridge(self)

    def uninstall(self, project: str | None, agents: tuple[Agent, ...]) -> None:
        """Tear down hook, bridges and the agents-dir content we own — or unwire one given project."""
        if project:
            self.unwire_project(Path(project).resolve(), agents)
            return
        # bridges first, then the agents dir they point into
        for agent in agents:
            agent.unregister(self)
            agent.unbridge(self)
        self.prune(self.rules_dir, set())
        rmdir_quiet(self.rules_dir)
        rmdir_quiet(self.agents_dir / "rules")
        if self.owned(self.agents_file):
            self.agents_file.unlink()
        rmdir_quiet(self.agents_dir)
        say(f"uninstalled from {self.agents_dir} and every bridged agent — the clone at {self.repo_dir} remains")

    def populate_agents_dir(self) -> None:
        """Land AGENTS.md and every rule in the agents dir — the one place agent dirs bridge into."""
        self.reconcile(self.by_name(self.shipped_rule_files()), self.rules_dir)
        self.symlink(self.repo_dir / "AGENTS.md", self.agents_file)

    def wire_project(self, project_dir: Path, agents: tuple[Agent, ...]) -> None:
        """Materialize the container in .agents/rules and let each agent bridge it; a missing declaration unwires."""
        container = project_dir / ".agents" / "rules" / self.namespace
        stacks = self.declared_stacks(project_dir)
        if not stacks:
            # dropping the declaration is the opt-out; frontmatter that parsed to nothing is a typo, not a decision
            if self.frontmatter(self.declaration_file(project_dir)):
                warn(f"no 'stacks: [...]' line in {self.declaration_file(project_dir)} — unwiring")
            # a removed declaration is the opt-out — everything we placed goes with it
            self.unwire_project(project_dir, agents)
            return
        container.mkdir(parents=True, exist_ok=True)
        self.symlink(self.PROJECT_MD_TARGET, container / "project.md")
        keep = {"project.md"}
        for stack in stacks:
            rule_target = self.rules_dir / f"{stack}.md"
            if rule_target.exists():
                self.symlink(rule_target, container / f"{stack}.md")
                keep.add(f"{stack}.md")
            else:
                warn(f"unknown stack '{stack}' in {project_dir}/AGENTS.md")
        self.prune(container, keep)
        for agent in agents:
            if agent.present():
                agent.bridge_project(self, project_dir)

    def unwire_project(self, project_dir: Path, agents: tuple[Agent, ...]) -> None:
        """Drop our container and every agent's per-project pointers."""
        agents_rules_dir = project_dir / ".agents" / "rules"
        # a prune with no keep-set removes everything of ours
        self.prune(agents_rules_dir / self.namespace, set())
        rmdir_quiet(agents_rules_dir / self.namespace)
        rmdir_quiet(agents_rules_dir)
        for agent in agents:
            agent.unbridge_project(self, project_dir)

    def report_wiring(self, project_dir: Path) -> None:
        stacks = self.declared_stacks(project_dir)
        if stacks:
            say(f"wired {project_dir} ({', '.join(stacks)})")
        else:
            say(f"nothing wired — no stacks declared in {project_dir}")

    def declared_stacks(self, project_dir: Path) -> list[str]:
        """The project's stacks: declaration — the opt-in; inline `stacks: [python, django]` form only."""
        for line in self.frontmatter(self.declaration_file(project_dir)):
            declaration = self.STACKS_RE.match(line)
            if declaration:
                return [stack.strip() for stack in declaration.group(1).split(",") if stack.strip()]
        return []

    def declaration_file(self, project_dir: Path) -> Path:
        return project_dir / "AGENTS.md"

    def frontmatter(self, markdown_file: Path) -> list[str]:
        """The lines between the leading --- fences — body text never reads as configuration."""
        if not markdown_file.is_file():
            return []
        lines = markdown_file.read_text().splitlines()
        if not lines or lines[0].strip() != "---":
            return []
        for position, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                return lines[1:position]
        return []

    def pull(self) -> bool:
        """Fast-forward the clone, reporting whether it worked — the session hook stays silent, install speaks up."""
        # macOS ships no timeout(1); subprocess provides the bound the hook otherwise had to enforce
        try:
            pulled = subprocess.run(
                ["git", "-C", str(self.repo_dir), "pull", "--ff-only", "--quiet"],
                timeout=self.PULL_TIMEOUT_SECONDS,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return False
        return pulled.returncode == 0

    def reconcile(self, links: dict[str, Path | str], into_dir: Path) -> None:
        """Link every target into the dir under its given name, pruning our links that no longer belong."""
        into_dir.mkdir(parents=True, exist_ok=True)
        for name, target in links.items():
            self.symlink(target, into_dir / name)
        self.prune(into_dir, set(links))

    def by_name(self, sources: list[Path]) -> dict[str, Path]:
        """Sources keyed by the name they keep in the destination dir."""
        return {source.name: source for source in sources}

    def symlink(self, target: Path | str, link_path: Path) -> None:  # argument order mirrors ln -s
        """Create the link unless the name is taken by something we don't own — then warn and step aside."""
        if (link_path.exists() or link_path.is_symlink()) and not self.owned(link_path):
            warn(f"{link_path} exists and is not ours — skipped")
            return
        link_path.unlink(missing_ok=True)
        try:
            link_path.symlink_to(target)
        except FileExistsError:
            # a concurrent sync won the unlink-to-create window — its link is identical
            pass

    def prune(self, scan_dir: Path, keep: set[str]) -> None:
        """Remove owned links whose name left the keep-set — upstream renames and deletions leave no zombies."""
        if not scan_dir.is_dir():
            return
        for entry in list(scan_dir.iterdir()):
            if self.owned(entry) and entry.name not in keep:
                entry.unlink(missing_ok=True)

    def owned(self, path: Path) -> bool:
        """A symlink is ours when it lands in this clone, or wears one of our project-relative shapes."""
        if not path.is_symlink():
            return False
        if os.readlink(path) in (self.PROJECT_MD_TARGET, self.PROJECT_RULES_TARGET, self.ASSISTANT_MD_TARGET):
            return True
        # following the agents-dir hop to its end keeps a second installation's links foreign — ours all land in our clone
        return path.resolve().is_relative_to(self.repo_dir)

    def is_stack_neutral(self, rule_file: Path) -> bool:
        """No paths: frontmatter means the rule loads everywhere — exactly those bridge globally."""
        return not any(line.startswith("paths:") for line in self.frontmatter(rule_file))

    def shipped_rule_files(self) -> list[Path]:
        return sorted((self.repo_dir / "rules").glob("*.md"))

    @property
    def rules_dir(self) -> Path:
        return self.agents_dir / "rules" / self.namespace

    @property
    def agents_file(self) -> Path:
        return self.agents_dir / "AGENTS.md"

