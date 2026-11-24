from __future__ import annotations

import os
from unittest.mock import patch

from loomwork.agents import ClaudeCode, OpenCode
from loomwork.loom import Loom
from tests.fixtures import SandboxTestCase


class ConfigDirTests(SandboxTestCase):
    """Which dir an agent is written for: the one passed on the command line, else its launch variable, else its standard one."""

    def test_an_agent_without_either_reads_its_standard_dir(self) -> None:
        self.assertEqual(ClaudeCode.from_config_dir().config_dir, self.home / ".claude")
        self.assertEqual(OpenCode.from_config_dir().config_dir, self.home / ".config" / "opencode")

    def test_the_launch_variable_beats_the_standard_dir(self) -> None:
        self.enterContext(patch.dict(os.environ, {ClaudeCode.CONFIG_DIR_ENV: "~/.claude-work"}))
        self.assertEqual(ClaudeCode.from_config_dir().config_dir, self.home / ".claude-work")

    def test_a_cli_config_dir_beats_the_launch_variable(self) -> None:
        self.enterContext(patch.dict(os.environ, {ClaudeCode.CONFIG_DIR_ENV: str(self.home / ".claude-work")}))
        cli_config_dir = self.home / ".claude-client"
        self.assertEqual(
            Loom(self.loom.registry, {ClaudeCode.NAME: cli_config_dir}).agents_named((ClaudeCode.NAME,))[0].config_dir,
            cli_config_dir,
        )

    def test_an_empty_launch_variable_counts_as_unset(self) -> None:
        self.enterContext(patch.dict(os.environ, {OpenCode.CONFIG_DIR_ENV: ""}))
        self.assertEqual(OpenCode.from_config_dir().config_dir, self.home / ".config" / "opencode")
