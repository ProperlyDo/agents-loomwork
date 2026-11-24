from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from loomwork import paths
from loomwork.output import warn
from loomwork.targets.declaration import Declaration

if TYPE_CHECKING:
    from pathlib import Path

    from loomwork.agents import Agent
    from loomwork.loom import Loom


@dataclass(frozen=True)
class WiringReport:
    """The report of wiring one target dir: what landed in its .agents/, and where each agent reads it from."""

    target_dir: Path
    declaration: Declaration | None
    # what actually landed, which a declaration naming something no source defines can differ from
    rules: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()
    # per agent name, the paths it reads this target dir's rules and skills through
    read_from: dict[str, tuple[Path, ...]] = field(default_factory=dict)
    # the directories the wiring changed, which an open session has yet to load
    updated: tuple[Path, ...] = ()

    def __str__(self) -> str:
        if self.declaration is None:
            return f"nothing wired — no {Declaration.FILE_NAME} in {self.target_dir}"
        return "\n".join([f"wired {self.target_dir}", *self._landed(), *self._read_by_agents()])

    def _landed(self) -> list[str]:
        """One report line per kind copied into .agents/ — or, when nothing was, a note that only the global rules apply."""
        kinds = (("rules", self.rules), ("skills", self.skills))
        landed = [f"  {paths.AGENTS_DIR_NAME}/{kind}: {', '.join(names)}" for kind, names in kinds if names]
        if not landed:
            return [f"  {paths.AGENTS_DIR_NAME}/rules: only what its sources hand every target dir"]
        return landed

    def _read_by_agents(self) -> list[str]:
        return [
            f"  {name} reads from {', '.join(paths.shown(path, self.target_dir) for path in read)}"
            for name, read in self.read_from.items()
        ]


class Wiring:
    """Wire one declared target dir for these agents: our copies in its .agents/, and each agent pointed at them."""

    def __init__(self, loom: Loom, target_dir: Path, declaration: Declaration, agents: tuple[Agent, ...]) -> None:
        self.loom = loom
        self.target_dir = target_dir
        self.declaration = declaration
        self.agents = agents
        self._declared_keys = loom.sources.declared_keys(target_dir)
        self._updated: list[Path] = []
        self._installation = loom.installation_of(self._declared_keys, self._updated)

    def run(self) -> WiringReport:
        # recorded first, since an agent's global rules come from what its dir's target dirs declare
        self._record_in_config_dirs()
        self._warn_about_undefined_names()
        # our copies before the agents' pointers, since those aim at them
        skills = self._place_skills()
        rules = self._place_rules()
        self._lay_global_files()
        read_from = self._point_agents_at_copies()
        return WiringReport(
            self.target_dir, self.declaration, rules, skills, read_from=read_from, updated=tuple(self._updated)
        )

    def _record_in_config_dirs(self) -> None:
        for agent in self.agents:
            self.loom.registry.add_config_dir(agent.config_dir, agent.NAME)
            self.loom.registry.add_target_dir(agent.config_dir, self.target_dir, self._declared_keys)

    def _warn_about_undefined_names(self) -> None:
        for undefined in self._installation.catalog.undefined(self.declaration):
            warn(f"unknown {undefined} in {self.target_dir / Declaration.FILE_NAME}")

    def _place_skills(self) -> tuple[str, ...]:
        wanted = self._installation.catalog.skill_folders(self.declaration.skills)
        return self._installation.place(wanted, paths.target_skills_dir(self.target_dir))

    def _place_rules(self) -> tuple[str, ...]:
        wanted = self._installation.catalog.rule_files(self.declaration.rules)
        return self._installation.place(wanted, paths.target_rules_dir(self.target_dir))

    def _lay_global_files(self) -> None:
        """Each agent's own config dir, from the sources that dir draws on rather than this target dir's alone."""
        for agent in self.agents:
            agent.lay_global_files(
                self.loom.installation_of(self.loom.sources.keys_of(agent.config_dir), self._updated)
            )

    def _point_agents_at_copies(self) -> dict[str, tuple[Path, ...]]:
        return {agent.NAME: agent.wire_target_dir(self._installation, self.target_dir) for agent in self.agents}
