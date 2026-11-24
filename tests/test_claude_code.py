from __future__ import annotations

import json
from unittest.mock import patch

from loomwork import paths
from loomwork.agents import ClaudeCode
from loomwork.sources.manifest import Manifest
from loomwork.targets.declaration import Declaration
from tests.fixtures import (
    InstallationTestCase,
    make_target_dir,
)


class ClaudeCodeTests(InstallationTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.claude_dir.mkdir(parents=True)
        self.agent = ClaudeCode(self.claude_dir)

    def test_a_source_that_hands_out_nothing_leaves_no_dir(self) -> None:
        (self.clone / Manifest.FILE_NAME).unlink()
        self.agent.lay_global_files(self.installation)
        self.assertFalse((self.claude_dir / "rules").exists())

    def test_only_rules_handed_to_everyone_are_laid_globally(self) -> None:
        self.agent.lay_global_files(self.installation)
        laid = self.claude_dir / "rules"
        self.assertEqual({entry.name for entry in laid.iterdir()}, {"git.md"})
        self.assertIn("# Agent Instructions", (self.claude_dir / "CLAUDE.md").read_text())

    def test_a_foreign_skill_survives_laying_the_global_files(self) -> None:
        theirs = self.claude_dir / "skills" / "theirs"
        theirs.mkdir(parents=True)
        self.agent.lay_global_files(self.installation)
        self.assertTrue(theirs.is_dir())

    def test_a_global_skill_is_copied_into_the_agents_own_skills_dir(self) -> None:
        (self.clone / "skills" / "everywhere").mkdir(parents=True)
        (self.clone / "skills" / "everywhere" / "SKILL.md").write_text("---\nname: everywhere\n---\n")
        (self.clone / Manifest.FILE_NAME).write_text('[global]\nskills = ["everywhere"]\n')

        self.agent.lay_global_files(self.installation)

        placed = self.claude_dir / "skills" / "everywhere"
        self.assertTrue((placed / "SKILL.md").is_file())
        self.assertFalse(placed.is_symlink())

    def test_unbridging_takes_back_the_global_skills_only(self) -> None:
        (self.clone / Manifest.FILE_NAME).write_text('[global]\nskills = ["translate"]\n')
        theirs = self.claude_dir / "skills" / "theirs"
        theirs.mkdir(parents=True)
        self.agent.lay_global_files(self.installation)
        self.agent.clear_global_files(self.installation)
        self.assertFalse((self.claude_dir / "skills" / "translate").exists())
        self.assertTrue(theirs.is_dir())

    def test_target_dir_rules_sit_beside_the_target_dirs_own(self) -> None:
        target_dir = make_target_dir(self.root)
        own = target_dir / ".claude" / "rules" / "team.md"
        own.parent.mkdir(parents=True)
        own.write_text("# Team\n")
        self.loom.wire(target_dir, (self.agent,))
        rules_link = target_dir / ".claude" / "rules" / "loom"
        # relative, because Claude never loads a project rule whose link resolves outside the project
        self.assertFalse(rules_link.readlink().is_absolute())
        self.assertEqual(rules_link.resolve(), paths.target_rules_dir(target_dir).resolve())
        self.assertEqual(own.read_text(), "# Team\n")

    def test_each_skill_is_linked_beside_the_target_dirs_own(self) -> None:
        target_dir = make_target_dir(self.root, skills=("translate",))
        own = target_dir / ".claude" / "skills" / "deploy"
        own.mkdir(parents=True)
        wanted = self.installation.catalog.skill_folders(("translate",))
        self.installation.place(wanted, paths.target_skills_dir(target_dir))
        self.loom.wire(target_dir, (self.agent,))
        self.assertTrue((target_dir / ".claude" / "skills" / "translate" / "SKILL.md").is_file())
        self.assertTrue(own.is_dir())

    def test_a_foreign_claude_md_is_left_alone_and_not_reported(self) -> None:
        (self.claude_dir / "CLAUDE.md").write_text("# Mine\n")
        self.assertNotIn(self.claude_dir / "CLAUDE.md", self.agent.lay_global_files(self.installation))
        self.assertEqual((self.claude_dir / "CLAUDE.md").read_text(), "# Mine\n")

    def hooks_in_settings(self) -> list[str]:
        entries = json.loads(self.agent._settings_file.read_text())["hooks"][ClaudeCode.HOOK_EVENT]
        return [hook["command"] for entry in entries for hook in entry["hooks"]]

    def write_foreign_hook(self) -> None:
        self.agent._settings_file.parent.mkdir(parents=True, exist_ok=True)
        foreign = {"hooks": {ClaudeCode.HOOK_EVENT: [{"hooks": [{"type": "command", "command": "echo theirs"}]}]}}
        self.agent._settings_file.write_text(json.dumps(foreign))

    def test_the_hook_runs_nothing_where_a_target_dir_never_opted_in(self) -> None:
        self.agent.lay_global_files(self.installation)
        command = self.hooks_in_settings()[0]
        self.assertIn(Declaration.FILE_NAME, command)
        self.assertIn("exit 0", command)
        self.assertTrue(command.endswith(f'sync --for {ClaudeCode.NAME} "$CLAUDE_PROJECT_DIR"'))

    def test_the_hook_names_the_config_dir_it_was_registered_in(self) -> None:
        # a sync tells the asking session's setup from another by the dir it reads
        self.agent.lay_global_files(self.installation)
        self.assertIn(f"{ClaudeCode.config_dir_option()} {self.claude_dir} sync", self.hooks_in_settings()[0])

    def test_a_hook_from_before_per_agent_dirs_is_replaced(self) -> None:
        self.agent._settings_file.parent.mkdir(parents=True, exist_ok=True)
        old = f"loom --config-dir {self.claude_dir} sync --for claude"
        self.agent._settings_file.write_text(
            json.dumps({"hooks": {ClaudeCode.HOOK_EVENT: [{"hooks": [{"command": old}]}]}})
        )
        self.agent.lay_global_files(self.installation)
        self.assertEqual(len(self.hooks_in_settings()), 1)
        self.assertIn(ClaudeCode.config_dir_option(), self.hooks_in_settings()[0])

    def test_the_hook_calls_loom_where_it_was_started_from(self) -> None:
        # run from a checkout with `uv run`, loom is on no PATH a hook's shell knows
        started = self.root / "checkout" / ".venv" / "bin" / "loom"
        started.parent.mkdir(parents=True)
        started.write_text("#!/bin/sh\n")
        started.chmod(0o755)
        with patch("sys.argv", [str(started)]):
            self.agent.lay_global_files(self.installation)
        self.assertTrue(self.hooks_in_settings()[0].split("; ", 1)[1].startswith(f"{started} --claude-config-dir"))

    def test_registering_twice_keeps_one_of_ours_and_every_foreign_hook(self) -> None:
        self.write_foreign_hook()
        self.agent.lay_global_files(self.installation)
        self.agent.lay_global_files(self.installation)
        commands = self.hooks_in_settings()
        self.assertEqual(commands.count("echo theirs"), 1)
        self.assertEqual(len([command for command in commands if " sync " in command]), 1)

    def test_unbridging_leaves_the_foreign_hooks(self) -> None:
        self.write_foreign_hook()
        self.agent.lay_global_files(self.installation)
        self.agent.clear_global_files(self.installation)
        self.assertEqual(self.hooks_in_settings(), ["echo theirs"])

    def test_a_hook_is_ours_whatever_path_it_was_written_with(self) -> None:
        for command in ("loom sync /x", "/opt/homebrew/bin/loom sync /x"):
            self.assertTrue(self.agent._is_our_hook({"command": command}), command)

    def test_a_foreign_sync_command_is_not_ours(self) -> None:
        self.assertFalse(self.agent._is_our_hook({"command": "rsync sync /x"}))
        self.assertFalse(self.agent._is_our_hook({"command": "echo loom sync"}))

    def test_a_source_without_one_still_hands_out_its_rules(self) -> None:
        (self.clone / "AGENTS.md").unlink()
        target_dir = make_target_dir(self.root, rules=("python",))
        self.agent.lay_global_files(self.installation)
        self.loom.wire(target_dir, (self.agent,))
        self.assertTrue((paths.target_rules_dir(target_dir) / "python.md").is_file())
        self.assertFalse((self.claude_dir / "CLAUDE.md").exists())
