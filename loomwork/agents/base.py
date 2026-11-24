from __future__ import annotations

import os
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Self

from loomwork import COMMAND_NAME, paths

if TYPE_CHECKING:
    from loomwork.installation import Installation


class Agent(ABC):
    """A supported agent in one config dir: global rules and skills go into `rules/` and `skills/` there.

    An empty TARGET_RULES_DIR or TARGET_SKILLS_DIR means the agent reads `.agents/` itself, so nothing is laid for it.
    A subclass names its standard_config_dir, and extends the lay and wire methods for surfaces of its own.
    """

    NAME: ClassVar[str]
    # what the agent is called on PATH
    COMMAND: ClassVar[str]
    # what the agent is launched with to read another config dir than its standard one
    CONFIG_DIR_ENV: ClassVar[str]
    # what the agent calls the file it reads instructions from; empty when it reads none
    AGENTS_MD_NAME: ClassVar[str] = ""
    # the dir in a target dir it reads rules from, recursively
    TARGET_RULES_DIR: ClassVar[str] = ""
    # the dir in a target dir it finds skills in, one level deep
    TARGET_SKILLS_DIR: ClassVar[str] = ""

    def __init__(self, config_dir: Path) -> None:
        # the root of the agent's user-level paths
        self.config_dir = config_dir

    @classmethod
    def from_config_dir(cls, config_dir: Path | None = None) -> Self:
        """The agent in this config dir, else in the one its launch variable names, else in its standard one."""
        # an empty variable counts as unset, as it does for the agents themselves
        chosen = config_dir or os.environ.get(cls.CONFIG_DIR_ENV)
        if not chosen:
            return cls(cls.standard_config_dir())
        return cls(Path(chosen).expanduser().absolute())

    def lay_global_files(self, installation: Installation) -> tuple[Path, ...]:
        """Lay every user-level surface this agent names a path for, naming what was laid."""
        return (
            *self._publish_agents_md(installation),
            *self._lay_global_rules(installation),
            *self.lay_global_skills(installation),
        )

    def clear_global_files(self, installation: Installation) -> None:
        """Mirror of lay_global_files(): what is ours goes, anything the user put there stays."""
        installation.clear_owned_in(self.skills_dir)
        installation.clear_owned_in(self.rules_dir)
        paths.remove_if_empty(self.rules_dir)
        if self.AGENTS_MD_NAME:
            published = self.config_dir / self.AGENTS_MD_NAME
            if installation.owns(published):
                published.unlink()
        # a dir only loom filled would otherwise stay behind empty
        paths.remove_if_empty(self.skills_dir)
        paths.remove_if_empty(self.config_dir)

    def wire_target_dir(self, installation: Installation, target_dir: Path) -> tuple[Path, ...]:
        """Point the agent at this target dir's rules and skills, naming where it reads them from."""
        return (
            *self._wire_target_rules(installation, target_dir),
            *self.wire_target_skills(installation, target_dir),
        )

    def unwire_target_dir(self, installation: Installation, target_dir: Path) -> None:
        """Drop our rule and skill links from the target dir, and the dirs when they empty out."""
        for relative in (self.TARGET_RULES_DIR, self.TARGET_SKILLS_DIR):
            if not relative:
                continue
            linked_dir = target_dir / relative
            self._drop_whole_dir_link(installation, linked_dir)
            installation.clear_owned_in(linked_dir)
            paths.remove_if_empty(linked_dir)
            paths.remove_if_empty(linked_dir.parent)

    def lay_global_skills(self, installation: Installation) -> tuple[Path, ...]:
        """Copy each globally wanted skill into the agent's own skills dir."""
        catalog = installation.catalog
        if not installation.place(catalog.skill_folders(catalog.global_skills), self.skills_dir):
            return ()
        return (self.skills_dir,)

    def wire_target_skills(self, installation: Installation, target_dir: Path) -> tuple[Path, ...]:
        """One link per skill, so the target dir's own skills stay beside ours."""
        skills = paths.target_skills_dir(target_dir)
        if not self.TARGET_SKILLS_DIR:
            if not skills.is_dir():
                return ()
            return (skills,)
        skills_dir = target_dir / self.TARGET_SKILLS_DIR
        self._drop_whole_dir_link(installation, skills_dir)
        placed = []
        if skills.is_dir():
            placed = sorted(skill for skill in skills.iterdir() if skill.is_dir())
        if not placed and not skills_dir.is_dir():
            return ()
        installation.place_links(
            {skill.name: paths.link_target(skill, skills_dir) for skill in placed},
            skills_dir,
        )
        paths.remove_if_empty(skills_dir)
        if not placed:
            return ()
        return (skills_dir,)

    def launch_note(self) -> str:
        """The launch hint for a dir the agent does not read by itself; empty for its standard one."""
        if self.reads_standard_dir():
            return ""
        return self.launch_hint()

    def launch_hint(self) -> str:
        """How to start the agent so it reads the dir we write into."""
        if self.reads_standard_dir():
            return f"launch {self.NAME} without {self.CONFIG_DIR_ENV}"
        return f"launch {self.NAME} as {self.CONFIG_DIR_ENV}={paths.shown(self.config_dir)} {self.COMMAND}"

    def target_folders(self) -> tuple[str, ...]:
        """The folders this agent is wired through at a target dir's root — what the target dir's .gitignore must cover."""
        relatives = (self.TARGET_RULES_DIR, self.TARGET_SKILLS_DIR)
        return tuple(sorted({Path(relative).parts[0] for relative in relatives if relative}))

    def is_present(self) -> bool:
        """Whether the agent itself is on this machine — its config dir cannot say, since we create that ourselves."""
        return bool(shutil.which(self.COMMAND))

    def counterpart_in(self, agents: tuple[Agent, ...]) -> Agent | None:
        """The agent of this kind among these, whichever dir it is in."""
        return next((agent for agent in agents if agent.NAME == self.NAME), None)

    def shares_dir_with(self, other: Agent) -> bool:
        return self.config_dir.resolve() == other.config_dir.resolve()

    def reads_standard_dir(self) -> bool:
        """Whether the agent finds this dir without being launched with CONFIG_DIR_ENV."""
        return self.config_dir.resolve() == self.standard_config_dir().resolve()

    def _publish_agents_md(self, installation: Installation) -> tuple[Path, ...]:
        """Write the source's AGENTS.md under the name this agent reads it by."""
        if not self.AGENTS_MD_NAME:
            return ()
        published = self.config_dir / self.AGENTS_MD_NAME
        agents_md = installation.catalog.agents_md
        if agents_md is None:
            # none of the sources this dir draws on hands one out any more
            if installation.owns(published):
                published.unlink()
            return ()
        installation.place_file(agents_md, published)
        # a file of the user's own was left alone, so it is not ours to report
        if not installation.owns(published):
            return ()
        return (published,)

    def _lay_global_rules(self, installation: Installation) -> tuple[Path, ...]:
        """Copy what the sources hand every target dir into the agent's own rules dir."""
        catalog = installation.catalog
        landed = installation.place(catalog.rule_files(catalog.global_rules), self.rules_dir)
        # a source that hands out nothing leaves no empty dir behind
        paths.remove_if_empty(self.rules_dir)
        if not landed:
            return ()
        return (self.rules_dir,)

    def _wire_target_rules(self, installation: Installation, target_dir: Path) -> tuple[Path, ...]:
        """Link .agents/rules one level down in the agent's rules dir, beside whatever the target dir keeps there."""
        copied_rules = paths.target_rules_dir(target_dir)
        if not self.TARGET_RULES_DIR:
            return (copied_rules,)
        rules_dir = target_dir / self.TARGET_RULES_DIR
        self._drop_whole_dir_link(installation, rules_dir)
        rules_dir.mkdir(parents=True, exist_ok=True)
        rules_link = rules_dir / COMMAND_NAME
        installation.symlink(
            paths.link_target(copied_rules, rules_dir),
            rules_link,
        )
        if not installation.owns(rules_link):
            return ()
        return (rules_link,)

    @staticmethod
    def _drop_whole_dir_link(installation: Installation, directory: Path) -> None:
        """A link of ours standing in for the whole dir would put the links meant for it inside .agents/."""
        if directory.is_symlink() and installation.owns(directory):
            directory.unlink()

    @classmethod
    @abstractmethod
    def standard_config_dir(cls) -> Path:
        """Where the agent keeps its config when launched without CONFIG_DIR_ENV."""

    @property
    def rules_dir(self) -> Path:
        return self.config_dir / "rules"

    @property
    def skills_dir(self) -> Path:
        return self.config_dir / "skills"

    @classmethod
    def config_dir_option(cls) -> str:
        """The command-line flag that gives this agent a config dir."""
        return f"--{cls.NAME}-config-dir"
