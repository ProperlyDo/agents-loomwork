from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from loomwork.agents import OpenCode
from loomwork.sources.manifest import Manifest
from tests.fixtures import (
    GLOBAL_RULE,
    InstallationTestCase,
    declare,
    make_target_dir,
)


class OpenCodeTests(InstallationTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.agent = OpenCode.from_config_dir()

    def make_manual_skill(self, name: str = "support") -> None:
        """Add a skill with `disable-model-invocation` to the source; its description needs YAML quoting."""
        skill = self.clone / "skills" / name
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: 'duty: the board'\ndisable-model-invocation: true\n---\n\nArguments: $ARGUMENTS\n"
        )

    def wire_with_skills(self, skills: tuple[str, ...]) -> Path:
        """Declare these skills, wire the target dir for OpenCode, and return its commands dir."""
        target_dir = self.root / "target_dir"
        if target_dir.is_dir():
            declare(target_dir, ("python",), skills=skills)
        else:
            make_target_dir(self.root, skills=skills)
        self.loom.wire(target_dir, (self.agent,))
        return target_dir / ".opencode" / "commands"

    def test_its_agents_file_comes_and_goes_with_the_global_files(self) -> None:
        self.agent.lay_global_files(self.installation)
        self.assertIn("# Agent Instructions", (self.agent.config_dir / "AGENTS.md").read_text())
        self.agent.clear_global_files(self.installation)
        self.assertFalse((self.agent.config_dir / "AGENTS.md").exists())

    def test_the_global_rules_land_in_its_rules_dir(self) -> None:
        self.agent.lay_global_files(self.installation)
        self.assertEqual({rule.name for rule in self.agent.rules_dir.iterdir()}, {"git.md"})
        self.assertNotIn(GLOBAL_RULE.strip(), (self.agent.config_dir / "AGENTS.md").read_text())

    def test_an_agent_that_never_ran_here_is_written_for_anyway(self) -> None:
        # loom distributes where it is told; a missing config dir is made, not a reason to refuse
        self.assertFalse(self.agent.config_dir.exists())
        self.agent.lay_global_files(self.installation)
        self.assertTrue((self.agent.config_dir / "AGENTS.md").is_file())

    def test_a_manual_skill_gets_a_command_that_loads_it(self) -> None:
        self.make_manual_skill()
        command = (self.wire_with_skills(("support",)) / "support.md").read_text()
        self.assertIn("description: 'duty: the board'", command)
        self.assertIn("`skill` tool with id `support`", command)
        # OpenCode replaces every occurrence, so a second one would repeat what was typed
        self.assertEqual(command.count("$ARGUMENTS"), 1)

    def test_a_manual_skill_without_a_description_gets_a_command_without_frontmatter(self) -> None:
        self.make_manual_skill()
        (self.clone / "skills" / "support" / "SKILL.md").write_text(
            "---\ndisable-model-invocation: true\n---\n\nDo it.\n"
        )
        command = (self.wire_with_skills(("support",)) / "support.md").read_text()
        self.assertTrue(command.startswith("Call the `skill` tool with id `support`"))

    def test_a_skill_the_model_may_start_gets_no_command(self) -> None:
        commands = self.wire_with_skills(("translate",))
        self.assertFalse(commands.exists())
        self.assertFalse(commands.parent.exists())

    def test_a_command_goes_when_its_skill_is_dropped(self) -> None:
        self.make_manual_skill()
        commands = self.wire_with_skills(("support",))
        own = commands / "deploy.md"
        own.write_text("Deploy $ARGUMENTS.\n")
        self.wire_with_skills(())
        self.assertEqual(list(commands.iterdir()), [own])

    def test_a_target_dirs_own_command_of_that_name_is_left_alone(self) -> None:
        self.make_manual_skill()
        own = make_target_dir(self.root, skills=("support",)) / ".opencode" / "commands" / "support.md"
        own.parent.mkdir(parents=True)
        own.write_text("Mine.\n")
        warning = self.stderr_of(lambda: self.wire_with_skills(("support",)))
        self.assertIn("not ours", warning)
        self.assertEqual(own.read_text(), "Mine.\n")

    def test_unwiring_takes_the_commands_and_the_folder_they_made(self) -> None:
        self.make_manual_skill()
        commands = self.wire_with_skills(("support",))
        self.agent.unwire_target_dir(self.installation, self.root / "target_dir")
        self.assertFalse(commands.parent.exists())

    def test_a_global_manual_skill_gets_a_command_in_the_config_dir(self) -> None:
        self.make_manual_skill()
        (self.clone / Manifest.FILE_NAME).write_text('[global]\nskills = ["support", "translate"]\n')
        commands = self.agent.commands_dir
        self.agent.lay_global_files(self.installation)
        self.assertEqual([command.name for command in commands.iterdir()], ["support.md"])
        self.agent.clear_global_files(self.installation)
        self.assertFalse(commands.exists())

    def test_an_empty_xdg_config_home_falls_back_to_the_home_config(self) -> None:
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": ""}):
            self.assertEqual(OpenCode.from_config_dir().config_dir, Path("~/.config/opencode").expanduser())
