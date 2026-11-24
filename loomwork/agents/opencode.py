from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

import yaml

from loomwork import paths
from loomwork.agents.base import Agent
from loomwork.sources.skill import Skill

if TYPE_CHECKING:
    from loomwork.installation import Installation


class OpenCode(Agent):
    """Instruction follower: its global AGENTS.md sends it to the rules, since it loads no rules dir on its own.

    OpenCode's / menu shows command files only. So for every manual skill (`disable-model-invocation: true`)
    we write a command that tells it to load that skill. Override `command_file()` to change its text.
    """

    NAME = "opencode"

    COMMAND = "opencode"
    AGENTS_MD_NAME = "AGENTS.md"
    CONFIG_DIR_ENV = "OPENCODE_CONFIG_DIR"
    # where OpenCode looks for a target dir's commands
    TARGET_COMMANDS_DIR: ClassVar[str] = ".opencode/commands"
    COMMAND_TEMPLATE: ClassVar[str] = (
        # the tool is named, since a model told only to load a skill goes looking for it on disk
        "Call the `skill` tool with id `{name}` and follow the instructions it returns.\n\n"
        # $ARGUMENTS appears once, since OpenCode replaces every occurrence with what was typed
        "Its arguments are the text between the tags, verbatim:\n<arguments>$ARGUMENTS</arguments>"
    )

    def clear_global_files(self, installation: Installation) -> None:
        """Also remove the commands we wrote into the config dir."""
        installation.clear_owned_in(self.commands_dir)
        paths.remove_if_empty(self.commands_dir)
        super().clear_global_files(installation)

    def unwire_target_dir(self, installation: Installation, target_dir: Path) -> None:
        """Also remove the commands we wrote into the target dir."""
        commands_dir = target_dir / self.TARGET_COMMANDS_DIR
        installation.clear_owned_in(commands_dir)
        paths.remove_if_empty(commands_dir)
        paths.remove_if_empty(commands_dir.parent)
        super().unwire_target_dir(installation, target_dir)

    def lay_global_skills(self, installation: Installation) -> tuple[Path, ...]:
        """Place the global skills, then write a command for each manual one."""
        laid = super().lay_global_skills(installation)
        catalog = installation.catalog
        skills = [Skill(folder) for folder in catalog.skill_folders(catalog.global_skills).values()]
        return laid + self._place_commands(installation, skills, self.commands_dir)

    def wire_target_skills(self, installation: Installation, target_dir: Path) -> tuple[Path, ...]:
        """Report where the target dir's skills are read from, then write a command for each manual one."""
        read_from = super().wire_target_skills(installation, target_dir)
        skills_dir = paths.target_skills_dir(target_dir)
        skills: list[Skill] = []
        if skills_dir.is_dir():
            skills = [Skill(folder) for folder in sorted(skills_dir.iterdir()) if folder.is_dir()]
        commands_dir = target_dir / self.TARGET_COMMANDS_DIR
        placed = self._place_commands(installation, skills, commands_dir)
        paths.remove_if_empty(commands_dir.parent)
        return read_from + placed

    def command_file(self, skill: Skill) -> str:
        """The command file's text: the skill's description as frontmatter, then `COMMAND_TEMPLATE` filled in."""
        prompt = self.COMMAND_TEMPLATE.format(name=skill.name)
        if not skill.description:
            return prompt
        # a description may hold YAML syntax, so it is dumped rather than formatted in
        described = yaml.safe_dump(
            {"description": skill.description},
            allow_unicode=True,
            # one line, however long the description
            width=float("inf"),
        )
        return f"{Skill.FRONTMATTER_FENCE}\n{described}{Skill.FRONTMATTER_FENCE}\n\n{prompt}"

    def launch_hint(self) -> str:
        """Also start it on a server of its own, since the shared one keeps the config dir of whoever started it."""
        if self.reads_standard_dir():
            return super().launch_hint()
        return (
            f"{super().launch_hint()} --standalone\n"
            f"  without --standalone, run '{self.COMMAND} service stop' first when another config dir was in use"
        )

    def target_folders(self) -> tuple[str, ...]:
        return tuple(sorted({*super().target_folders(), Path(self.TARGET_COMMANDS_DIR).parts[0]}))

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

    @classmethod
    def standard_config_dir(cls) -> Path:
        # OpenCode treats an empty XDG_CONFIG_HOME as unset
        return Path(os.environ.get("XDG_CONFIG_HOME") or "~/.config").expanduser() / "opencode"

    @property
    def commands_dir(self) -> Path:
        return self.config_dir / "commands"
