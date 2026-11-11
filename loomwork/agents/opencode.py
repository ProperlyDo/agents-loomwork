from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import ClassVar

import yaml

from loomwork import paths
from loomwork.agents.base import Agent
from loomwork.installation import Installation
from loomwork.skill import Skill


class OpenCode(Agent):
    """Instruction follower: its global AGENTS.md sends it to the rules, since it loads no rules dir on its own.

    OpenCode's / menu shows command files only. So for every manual skill (`disable-model-invocation: true`)
    we write a command that tells it to load that skill. Override `command_file()` to change its text.
    """

    NAME = "opencode"

    COMMAND = "opencode"
    AGENTS_MD_NAME = "AGENTS.md"
    # where OpenCode looks for a project's commands
    PROJECT_COMMANDS_DIR: ClassVar[str] = ".opencode/commands"
    # the tool is named, since a model told only to load a skill goes looking for it on disk
    # $ARGUMENTS appears once, since OpenCode replaces every occurrence with what was typed
    COMMAND_TEMPLATE: ClassVar[str] = (
        "Call the `skill` tool with id `{name}` and follow the instructions it returns.\n\n"
        "Its arguments are the text between the tags, verbatim:\n<arguments>$ARGUMENTS</arguments>"
    )

    @property
    def config_dir(self) -> Path:
        # the XDG spec's config root, where an empty value counts as unset — as it does for OpenCode
        return Path(os.environ.get("XDG_CONFIG_HOME") or "~/.config").expanduser() / "opencode"

    @property
    def commands_dir(self) -> Path:
        return self.config_dir / "commands"

    def unbridge(self, installation: Installation) -> None:
        """Also remove the commands we wrote into the config dir."""
        installation.clear_owned_in(self.commands_dir)
        paths.remove_if_empty(self.commands_dir)
        super().unbridge(installation)

    def unbridge_project(self, installation: Installation, project_dir: Path) -> None:
        """Also remove the commands we wrote into the project."""
        commands_dir = project_dir / self.PROJECT_COMMANDS_DIR
        installation.clear_owned_in(commands_dir)
        paths.remove_if_empty(commands_dir)
        paths.remove_if_empty(commands_dir.parent)
        super().unbridge_project(installation, project_dir)

    def project_folders(self) -> tuple[str, ...]:
        return tuple(sorted({*super().project_folders(), Path(self.PROJECT_COMMANDS_DIR).parts[0]}))

    def bridge_global_skills(self, installation: Installation) -> tuple[Path, ...]:
        """Place the global skills, then write a command for each manual one."""
        laid = super().bridge_global_skills(installation)
        catalog = installation.catalog
        skills = [Skill(folder) for folder in catalog.skill_folders(catalog.global_skills).values()]
        return laid + self._place_commands(installation, skills, self.commands_dir)

    def bridge_project_skills(self, installation: Installation, project_dir: Path) -> tuple[Path, ...]:
        """Report where the project's skills are read from, then write a command for each manual one."""
        read_from = super().bridge_project_skills(installation, project_dir)
        skills_dir = paths.project_skills_dir(project_dir)
        skills: list[Skill] = []
        if skills_dir.is_dir():
            skills = [Skill(folder) for folder in sorted(skills_dir.iterdir()) if folder.is_dir()]
        commands_dir = project_dir / self.PROJECT_COMMANDS_DIR
        placed = self._place_commands(installation, skills, commands_dir)
        paths.remove_if_empty(commands_dir.parent)
        return read_from + placed

    def command_file(self, skill: Skill) -> str:
        """The command file's text: the skill's description as frontmatter, then `COMMAND_TEMPLATE` filled in."""
        prompt = self.COMMAND_TEMPLATE.format(name=skill.name)
        if not skill.description:
            return prompt
        # safe_dump quotes a description that contains YAML syntax
        described = yaml.safe_dump({"description": skill.description}, allow_unicode=True, width=float("inf"))
        return f"{Skill.FRONTMATTER_FENCE}\n{described}{Skill.FRONTMATTER_FENCE}\n\n{prompt}"

    def _place_commands(self, installation: Installation, skills: list[Skill], commands_dir: Path) -> tuple[Path, ...]:
        """Write one command into commands_dir for each manual skill among these."""
        with tempfile.TemporaryDirectory() as generated_dir:
            generated: dict[str, Path] = {}
            for skill in skills:
                if not skill.is_manual:
                    continue
                # place() copies files, so the text goes to a temp file first
                generated[skill.name] = Path(generated_dir) / f"{skill.name}.md"
                generated[skill.name].write_text(self.command_file(skill))
            landed = installation.place(generated, commands_dir)
        paths.remove_if_empty(commands_dir)
        if not landed:
            return ()
        return (commands_dir,)
