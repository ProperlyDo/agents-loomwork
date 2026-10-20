from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from loomwork import COMMAND_NAME, git, paths, sources
from loomwork.agents import Agent, ClaudeCode, roster
from loomwork.declaration import Declaration, DeclaredSource, Manifest
from loomwork.installation import Installation
from loomwork.output import error, info, warn
from loomwork.registry import Registry
from loomwork.sources import Catalog


@dataclass(frozen=True)
class WiringReport:
    """The report of wiring one project: what landed in its .agents/, and where each agent reads it from."""

    project_dir: Path
    declaration: Declaration | None
    # what actually landed, which a declaration naming something no source defines can differ from
    rules: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()
    # per agent name, the paths it reads this project's rules and skills through
    read_from: dict[str, tuple[Path, ...]] = field(default_factory=dict)

    def __str__(self) -> str:
        if self.declaration is None:
            return f"nothing wired — no {Declaration.FILE_NAME} in {self.project_dir}"
        return "\n".join([f"wired {self.project_dir}", *self._landed(), *self._read_by_agents()])

    def _landed(self) -> list[str]:
        """One report line per kind copied into .agents/ — or, when nothing was, a note that only the global rules apply."""
        kinds = (("rules", self.rules), ("skills", self.skills))
        return [f"  {paths.AGENTS_DIR_NAME}/{kind}: {', '.join(names)}" for kind, names in kinds if names] or [
            f"  {paths.AGENTS_DIR_NAME}/rules: only what its sources hand every project"
        ]

    def _read_by_agents(self) -> list[str]:
        return [
            f"  {name} reads from {', '.join(paths.shown(path, self.project_dir) for path in read)}"
            for name, read in self.read_from.items()
        ]


@dataclass(frozen=True)
class Loom:
    """What one profile can do with its rules sources: the Claude config dir it lives in, and the projects that declare them."""

    config_dir: Path

    def init(self, project: Path, chosen: tuple[str, ...], source: str | Path | None = None) -> None:
        """Once per profile: add a source and set up the agents asked for — never one that was not."""
        if source:
            self.add_source(str(source))
        else:
            # a committed declaration names the rules and where to get them, so nothing needs asking or passing
            self.add_declared_sources(project)
        self._warn_about_gone_sources()
        installation = self.installation()
        for agent in self.agents_named(chosen):
            laid = agent.bridge(installation)
            if laid:
                info("\n".join([f"wired {agent.NAME}", *(f"  {paths.shown(path)}" for path in laid)]))
        if ClaudeCode.NAME in chosen and self.config_dir != ClaudeCode.DEFAULT_CONFIG_DIR:
            # we write where they said; Claude reads its own default unless it is launched the same way
            info(f"launch claude with {ClaudeCode.CONFIG_DIR_ENV}={self.config_dir}")

    def add(self, project: Path, chosen: tuple[str, ...]) -> None:
        """Wire a project for the chosen agents, fetching what it declares that this profile lacks."""
        self.add_declared_sources(project)
        dropped = [name for name in self.registry.agents_for(project) if name not in chosen]
        installation = self.installation()
        for agent in self.agents_named(tuple(dropped)):
            agent.unbridge_project(installation, project)
            info(f"unwired {agent.NAME} from {project}")
        self.registry.add_project(project, list(chosen))
        info(str(self.wire(installation, project)))
        installed = {agent.NAME for agent in self.present()}
        absent = [name for name in chosen if name not in installed]
        if absent:
            # recorded all the same: loom distributes where it is told, installed here or not
            warn(f"{', '.join(absent)} is not installed here — its files are written where it will look for them")

    def remove(self, project: Path) -> None:
        self._unwire(self.installation(), project, self.agents_for(project))
        if self.registry.drop_project(project):
            info(f"dropped {project}")
        else:
            warn(f"{project} was not wired in this profile — unwired it anyway")

    def sync(self, project: Path | None, asked_by: str | None = None) -> None:
        """Refresh one project from the sources it declares, or every wired one when none is named."""
        if project is None:
            self._sync_every_project()
            return
        # a project we know losing its declaration is the opt-out, and that still has to be undone
        if not Declaration.read(project) and not self.registry.knows_project(project):
            warn(f"{project} carries no {Declaration.FILE_NAME} — nothing to sync")
            return
        # a source added to the declaration since the last run is added here, so a pull is all a teammate needs
        self.add_declared_sources(project)
        self.refresh()
        installation = self.installation()
        info(str(self.wire(installation, project, asked_by)))
        _ask_for_a_restart(installation)

    def status(self) -> None:
        if not self.registry.sources:
            warn(f"no source yet — run '{COMMAND_NAME} init --source <path-to-rules-repo>'")
        for source, given in self.registry.added_sources:
            info(f"source {given}")
            if str(source) != given:
                info(f"  cloned at {source}")
            # the one thing no project's declaration shows: what its sources hand out anyway
            catalog = Catalog.of(source)
            for kind, names in (("rules", catalog.global_rules), ("skills", catalog.global_skills)):
                if names:
                    info(f"  every project gets {kind}: {', '.join(names)}")
        for project_dir in self.registry.projects:
            declaration = Declaration.read(project_dir) if project_dir.is_dir() else None
            if declaration is None:
                info(f"project {project_dir} — no {Declaration.FILE_NAME}")
                continue
            info(f"project {project_dir}")
            for kind, names in (("rules", declaration.rules), ("skills", declaration.skills)):
                if names:
                    info(f"  {kind}: {', '.join(names)}")
        if not self.registry.projects:
            info("no projects yet — one is recorded the first time it is wired")

    def uninstall(self) -> None:
        """Undo everything this profile installed: every project, then every agent's bridges and the registry."""
        installation = self.installation()
        for project_dir in self.registry.projects:
            if project_dir.is_dir():
                self._unwire(installation, project_dir, self.agents_for(project_dir))
        # every agent, installed or not: loom writes for an agent before it is installed, and only what it owns goes
        for agent in self.agents:
            agent.unbridge(installation)
        info(f"unbridged every agent — the clones in {paths.SOURCES_DIR.parent} remain")
        self.registry.forget()

    def wire(self, installation: Installation, project: Path, asked_by: str | None = None) -> WiringReport:
        """Wire one project and record it, whoever triggered it."""
        agents = self.agents_for(project, asked_by)
        for agent in agents:
            agent.bridge(installation)
        declaration = Declaration.read(project)
        if declaration is None:
            # a removed declaration is the opt-out — everything we placed goes with it
            self._unwire(installation, project, agents)
            self.registry.drop_project(project)
            return WiringReport(project, None)
        catalog = installation.catalog
        _warn_undefined(declaration, catalog, project / Declaration.FILE_NAME)
        # our copies in .agents/ first, since each agent's pointers aim at them
        skills = installation.place(catalog.skill_folders(declaration.skills), paths.project_skills_dir(project))
        rules = installation.place(catalog.rule_files(declaration.rules), paths.project_rules_dir(project))
        report = WiringReport(
            project,
            declaration,
            rules=rules,
            skills=skills,
            read_from={agent.NAME: agent.bridge_project(installation, project) for agent in agents},
        )
        self.registry.add_project(project, [agent.NAME for agent in agents])
        return report

    def add_declared_sources(self, project: Path) -> None:
        """Add each source the project declares that this profile lacks, or whose working copy replaced its clone."""
        declaration = Declaration.read(project)
        if declaration is None:
            return
        for declared in declaration.sources:
            # a relative path counts from the project, wherever loom happens to run from
            spelled = paths.resolved_from(declared.source, project)
            key = sources.identity(spelled)
            checkout = paths.as_path(spelled)
            known = self.registry.source_for(key)
            # a working copy of a repo we already cloned is what its author edits, so it replaces the clone
            repointed = checkout is not None and checkout.is_dir() and known != checkout.resolve()
            # a clone deleted since it was added is fetched again, like a source never added
            if known is None or not known.is_dir() or repointed:
                self.add_source(spelled)

    def add_source(self, source: str) -> Path:
        """Fetch a source and every source it builds on, record them in this profile, and return where it sits."""
        return self._add_source(source, seen={})

    def declare(self, project: Path, sources: tuple[DeclaredSource, ...]) -> None:
        """Write the project's opt-in: which sources it uses, and what it takes from each."""
        declared = Declaration(sources)
        info(f"declared {declared.write(project)}")
        if not declared.rules and not declared.skills:
            warn("nothing declared — this project gets only what its sources hand every project")

    def refresh(self) -> None:
        """Bring every source up to date before anything is copied from it."""
        self._warn_about_gone_sources()
        present = [source for source in self.registry.sources if source.is_dir()]
        # once per repo: two sources in subdirectories of one clone would otherwise race for its lock
        checkouts = list(dict.fromkeys(git.root(source) for source in present))
        if not checkouts:
            return
        # concurrently, because each update is a round trip and they do not depend on each other
        with ThreadPoolExecutor(max_workers=len(checkouts)) as updating:
            updated = list(updating.map(sources.update, checkouts))
        for checkout, worked in zip(checkouts, updated, strict=True):
            if not worked:
                warn(f"could not update {checkout} — using it as it stands")

    def ignore_what_we_write(self, project: Path) -> None:
        """Append our paths to .gitignore — the caller asks first, since the file is the project's own."""
        wanted = self.unignored(project)
        if not wanted:
            return
        block = f"# written per machine by {COMMAND_NAME}, from {Declaration.FILE_NAME}\n" + "\n".join(wanted) + "\n"
        existing = _gitignore_text(project)
        if existing:
            block = existing.rstrip("\n") + "\n\n" + block
        (project / ".gitignore").write_text(block)
        info(f"ignored {', '.join(wanted)} in .gitignore")

    def installation(self) -> Installation:
        """The sources added to this profile, as something that can act."""
        if not self.registry.sources:
            error(f"no source yet — run '{COMMAND_NAME} init --source <path-to-rules-repo>'")
        return Installation(catalog=Catalog.of(*self.registry.sources), registry=self.registry)

    def agents_named(self, names: tuple[str, ...]) -> tuple[Agent, ...]:
        """The agents behind the names a caller picked — loom touches these and no others."""
        return tuple(agent for agent in self.agents if agent.NAME in names)

    def agents_for(self, project_dir: Path, asked_by: str | None = None) -> tuple[Agent, ...]:
        """The agents this project was set up for, and the one asking: an agent whose session runs here is one it uses."""
        named = list(self.registry.agents_for(project_dir))
        if asked_by:
            named.append(asked_by)
        return self.agents_named(tuple(named))

    def usual_agents(self, project: Path) -> tuple[str, ...]:
        """What a project is likely wired for: what it was set up for, or on a first run whatever is installed here."""
        if self.registry.knows_project(project):
            return tuple(self.registry.agents_for(project))
        return tuple(agent.NAME for agent in self.present())

    def present(self) -> tuple[Agent, ...]:
        return tuple(agent for agent in self.agents if agent.is_present())

    def most_declared_source(self) -> str | None:
        """The source most projects here declare — the likely answer for one more of the same."""
        declarations = [Declaration.read(project) for project in self.registry.projects]
        declared = [entry.source for declaration in declarations if declaration for entry in declaration.sources]
        return max(declared, key=declared.count, default=None)

    def unignored(self, project: Path) -> list[str]:
        """What we write into a project that its .gitignore does not cover yet."""
        # whole lines, since .claude/settings.local.json contains .claude/ yet leaves the rest of it unignored
        ignored = {line.strip().strip("/") for line in _gitignore_text(project).splitlines()}
        return [path for path in self.generated if path.strip("/") not in ignored]

    @property
    def registry(self) -> Registry:
        """Our state sits beside the config dir, so each profile — personal, work — keeps its own."""
        return Registry(path=self.config_dir / Registry.FILE_NAME)

    @property
    def agents(self) -> tuple[Agent, ...]:
        return roster(self.config_dir)

    @property
    def generated(self) -> tuple[str, ...]:
        """What loom writes into a project, as .gitignore lines: its .agents/, and every agent's own folders."""
        folders = {folder for agent in self.agents for folder in agent.project_folders()}
        return (f"{paths.AGENTS_DIR_NAME}/", *(f"{folder}/" for folder in sorted(folders)))

    def _unwire(self, installation: Installation, project: Path, agents: tuple[Agent, ...]) -> None:
        """Mirror of wire(): each agent's pointers, then our copies — rules and skills alike."""
        for agent in agents:
            agent.unbridge_project(installation, project)
        for placed_dir in (paths.project_rules_dir(project), paths.project_skills_dir(project)):
            installation.clear_owned_in(placed_dir)
            paths.remove_if_empty(placed_dir)
        paths.remove_if_empty(project / paths.AGENTS_DIR_NAME)

    def _sync_every_project(self) -> None:
        """The profile-wide pass: the sources updated once, then every project it wired."""
        if not self.registry.projects:
            info(f"no projects yet — '{COMMAND_NAME} init' takes one on")
            return
        self.refresh()
        for project_dir in self.registry.projects:
            if not project_dir.is_dir():
                warn(f"{project_dir} is gone — dropping it")
                self.registry.drop_project(project_dir)
                continue
            self.add_declared_sources(project_dir)
            installation = self.installation()
            info(str(self.wire(installation, project_dir)))
            _ask_for_a_restart(installation)

    def _warn_about_gone_sources(self) -> None:
        """Name each source no longer where it was added — the ones a project declares are fetched before this."""
        for source, given in self.registry.added_sources:
            if source.is_dir():
                continue
            if paths.as_path(given) is not None:
                warn(f"source {given} is gone — point '{COMMAND_NAME} init --source' at where it lives now")
            else:
                warn(
                    f"source {given} is gone from {source} — run '{COMMAND_NAME} init --source {given}' to fetch it again"
                )

    def _add_source(self, source: str, seen: dict[str, Path]) -> Path:
        key = sources.identity(source)
        # sources that build on each other in a loop stop at the first one met again
        if key in seen:
            return seen[key]
        checkout = sources.fetch(source)
        seen[key] = checkout
        # what a source builds on is recorded before it, so the source itself wins a filename they share
        for base in Manifest.read(checkout).builds_on:
            self._add_source(paths.resolved_from(base, checkout), seen)
        if self.registry.source_for(key) is None:
            info(f"added source {source}")
        self.registry.add_source(key, checkout, source)
        return checkout


def _gitignore_text(project: Path) -> str:
    ignore_file = project / ".gitignore"
    if not ignore_file.is_file():
        return ""
    return ignore_file.read_text()


def _ask_for_a_restart(installation: Installation) -> None:
    if not installation.updated:
        return
    updated = ", ".join(paths.shown(directory) for directory in installation.updated)
    # an open session read what was here at its launch
    info(f"updated {updated} — restart any open session to load it")


def _warn_undefined(declaration: Declaration, catalog: Catalog, declared_in: Path) -> None:
    """Name each rule or skill the project declares that no source defines."""
    kinds = (("rule", declaration.rules, catalog.rules), ("skill", declaration.skills, catalog.skills))
    for kind, names, defined in kinds:
        for name in names:
            if name not in defined:
                warn(f"unknown {kind} '{name}' in {declared_in}")
