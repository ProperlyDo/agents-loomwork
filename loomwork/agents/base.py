from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar

from loomwork import COMMAND_NAME, paths
from loomwork.installation import Installation


class Agent(ABC):
    """A supported agent: global rules and skills go into `rules/` and `skills/` in its config dir.

    An empty project path means the agent reads `.agents/` in the project itself, so nothing is laid for it there.
    """

    NAME: ClassVar[str]
    # what the agent is called on PATH
    COMMAND: ClassVar[str]
    # what the agent calls the file it reads instructions from; empty when it reads none
    AGENTS_MD_NAME: ClassVar[str] = ""
    # the dir in a project it reads rules from, recursively
    PROJECT_RULES_DIR: ClassVar[str] = ""
    # the dir in a project it finds skills in, one level deep
    PROJECT_SKILLS_DIR: ClassVar[str] = ""

    @property
    @abstractmethod
    def config_dir(self) -> Path:
        """Where the agent keeps its own configuration — our presence marker, and the root of its user-level paths."""

    def bridge(self, installation: Installation) -> tuple[Path, ...]:
        """Lay every user-level surface this agent names a path for, naming what was laid."""
        return (
            *self._publish_agents_md(installation),
            *self._bridge_global_rules(installation),
            *self._bridge_global_skills(installation),
        )

    def unbridge(self, installation: Installation) -> None:
        """Mirror of bridge(): what is ours goes, anything the user put there stays."""
        installation.clear_owned_in(self.config_dir / "skills")
        rules_dir = self.config_dir / "rules"
        installation.clear_owned_in(rules_dir)
        paths.remove_if_empty(rules_dir)
        if self.AGENTS_MD_NAME:
            published = self.config_dir / self.AGENTS_MD_NAME
            if installation.owned(published):
                published.unlink()

    def bridge_project(self, installation: Installation, project_dir: Path) -> tuple[Path, ...]:
        """Point the agent at this project's rules and skills, naming where it reads them from."""
        return (
            *self._bridge_project_rules(installation, project_dir),
            *self._bridge_project_skills(installation, project_dir),
        )

    def unbridge_project(self, installation: Installation, project_dir: Path) -> None:
        """Drop our rule and skill links from the project, and the dirs when they empty out."""
        for relative in (self.PROJECT_RULES_DIR, self.PROJECT_SKILLS_DIR):
            if not relative:
                continue
            linked_dir = project_dir / relative
            self._drop_whole_dir_link(installation, linked_dir)
            installation.clear_owned_in(linked_dir)
            paths.remove_if_empty(linked_dir)
            paths.remove_if_empty(linked_dir.parent)

    def project_folders(self) -> tuple[str, ...]:
        """The folders this agent's bridges live in at a project's root — what the project's .gitignore must cover."""
        relatives = (self.PROJECT_RULES_DIR, self.PROJECT_SKILLS_DIR)
        return tuple(sorted({Path(relative).parts[0] for relative in relatives if relative}))

    def is_present(self) -> bool:
        """Whether the agent itself is on this machine — its config dir cannot say, since we create that ourselves."""
        return bool(shutil.which(self.COMMAND))

    def _publish_agents_md(self, installation: Installation) -> tuple[Path, ...]:
        """Write the source's AGENTS.md under the name this agent reads it by."""
        agents_md = installation.catalog.agents_md
        if not self.AGENTS_MD_NAME or agents_md is None:
            return ()
        published = self.config_dir / self.AGENTS_MD_NAME
        installation.place_file(agents_md, published)
        # a file of the user's own was left alone, so it is not ours to report
        if not installation.owned(published):
            return ()
        return (published,)

    def _bridge_global_rules(self, installation: Installation) -> tuple[Path, ...]:
        """Copy what the sources hand every project into the agent's own rules dir."""
        rules_dir = self.config_dir / "rules"
        catalog = installation.catalog
        landed = installation.place(catalog.rule_files(catalog.global_rules), rules_dir)
        # a source that hands out nothing leaves no empty dir behind
        paths.remove_if_empty(rules_dir)
        if not landed:
            return ()
        return (rules_dir,)

    def _bridge_global_skills(self, installation: Installation) -> tuple[Path, ...]:
        """Copy each globally wanted skill into the agent's own skills dir."""
        skills_dir = self.config_dir / "skills"
        catalog = installation.catalog
        if not installation.place(catalog.skill_folders(catalog.global_skills), skills_dir):
            return ()
        return (skills_dir,)

    def _bridge_project_rules(self, installation: Installation, project_dir: Path) -> tuple[Path, ...]:
        """Link .agents/rules one level down in the agent's rules dir, beside whatever the project keeps there."""
        copied_rules = paths.project_rules_dir(project_dir)
        if not self.PROJECT_RULES_DIR:
            return (copied_rules,)
        rules_dir = project_dir / self.PROJECT_RULES_DIR
        self._drop_whole_dir_link(installation, rules_dir)
        rules_dir.mkdir(parents=True, exist_ok=True)
        rules_link = rules_dir / COMMAND_NAME
        installation.symlink(
            paths.link_target(copied_rules, rules_dir),
            rules_link,
        )
        if not installation.owned(rules_link):
            return ()
        return (rules_link,)

    def _bridge_project_skills(self, installation: Installation, project_dir: Path) -> tuple[Path, ...]:
        """One link per skill, since skills are found one level deep and the project's own stay beside ours."""
        skills = paths.project_skills_dir(project_dir)
        if not self.PROJECT_SKILLS_DIR:
            if not skills.is_dir():
                return ()
            return (skills,)
        skills_dir = project_dir / self.PROJECT_SKILLS_DIR
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

    def _drop_whole_dir_link(self, installation: Installation, directory: Path) -> None:
        """A link of ours standing in for the whole dir would put the links meant for it inside .agents/."""
        if directory.is_symlink() and installation.owned(directory):
            directory.unlink()
