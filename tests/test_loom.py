from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from loomwork.agents import ClaudeCode, JetBrains, OpenCode
from loomwork.declaration import Declaration
from loomwork.loom import Loom
from loomwork.registry import Registry
from tests.test_installation import make_clone, make_project, sandboxed_config_dirs


class SourceResolutionTests(unittest.TestCase):
    """Where a run takes its rules from: the plugin copy Claude invoked, or the clone `init` remembered."""

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(lambda: __import__("shutil").rmtree(self.root, ignore_errors=True))
        sandbox = sandboxed_config_dirs(self.root)
        sandbox.start()
        self.addCleanup(sandbox.stop)
        self.registry = Registry(path=self.root / ".loomwork.json")
        self.plugin = self.root / "plugin"
        (self.plugin / ".claude-plugin").mkdir(parents=True)
        (self.plugin / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "loomwork"}))
        (self.plugin / "AGENTS.md").write_text("# Agent Instructions\n")

    def as_plugin(self):
        return patch.dict(os.environ, {ClaudeCode.PLUGIN_ROOT_ENV: str(self.plugin)})

    def test_without_a_source_it_says_what_to_run(self) -> None:
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(SystemExit):
            _ = Loom(registry=self.registry).installation

    def test_the_plugin_names_itself_when_init_never_ran(self) -> None:
        with self.as_plugin():
            installation = Loom(registry=self.registry).installation
        self.assertEqual(installation.source, self.plugin)
        self.assertEqual(installation.namespace, "loomwork")

    def test_the_plugin_copy_wins_over_a_remembered_clone(self) -> None:
        # the clone can be stale or gone; the copy Claude just loaded is the live one
        self.registry.remember_source(self.root / "clone", "acme")
        with self.as_plugin():
            installation = Loom(registry=self.registry).installation
        self.assertEqual(installation.source, self.plugin)

    def test_a_namespace_from_init_survives_a_plugin_run(self) -> None:
        # otherwise the containers it already wrote would be orphaned under a new name
        self.registry.remember_source(self.root / "clone", "acme")
        with self.as_plugin():
            self.assertEqual(Loom(registry=self.registry).installation.namespace, "acme")

    def test_without_the_plugin_it_falls_back_to_the_clone(self) -> None:
        self.registry.remember_source(self.root / "clone", "acme")
        with patch.dict(os.environ, {}, clear=True):
            installation = Loom(registry=self.registry).installation
        self.assertEqual(installation.source, self.root / "clone")


if __name__ == "__main__":
    unittest.main()


class RegistryFollowsWiringTests(unittest.TestCase):
    """Whatever wires a project records it — a hook-driven sync counts as much as a hand-typed add."""

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(lambda: __import__("shutil").rmtree(self.root, ignore_errors=True))
        sandbox = sandboxed_config_dirs(self.root)
        sandbox.start()
        self.addCleanup(sandbox.stop)
        self.clone = make_clone(self.root)
        self.project = make_project(self.root)
        # the agents dir is passed explicitly: a test that uses the default writes into the real ~/.agents
        self.loom = Loom(
            registry=Registry(path=self.root / ".loomwork.json"), agents_dir=self.root / "home" / ".agents"
        )
        self.loom.registry.remember_source(self.clone, "acme")
        muted = patch("sys.stdout", new_callable=io.StringIO)
        muted.start()
        self.addCleanup(muted.stop)

    def test_a_hook_driven_sync_records_the_project(self) -> None:
        self.loom.sync(self.project)
        self.assertEqual(self.loom.registry.projects, [self.project])

    def test_a_project_that_dropped_its_declaration_is_forgotten(self) -> None:
        self.loom.sync(self.project)
        (self.project / Declaration.FILE_NAME).unlink()
        self.loom.sync(self.project)
        self.assertEqual(self.loom.registry.projects, [])


class ChosenAgentsTests(unittest.TestCase):
    """Which tools a project is wired for: what it chose, else the tool asking, else everything present."""

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(lambda: __import__("shutil").rmtree(self.root, ignore_errors=True))
        sandbox = sandboxed_config_dirs(self.root)
        sandbox.start()
        self.addCleanup(sandbox.stop)
        self.loom = Loom(registry=Registry(path=self.root / ".loomwork.json"), agents_dir=self.root / ".agents")
        self.project = self.root / "project"

    def test_a_recorded_choice_is_what_gets_wired(self) -> None:
        self.loom.registry.add(self.project, ["jetbrains"])
        self.assertEqual([agent.NAME for agent in self.loom.agents_for(self.project)], ["jetbrains"])

    def test_a_plugin_run_on_an_unknown_project_wires_claude_alone(self) -> None:
        plugin = self.root / "plugin"
        (plugin / ".claude-plugin").mkdir(parents=True)
        (plugin / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "loomwork"}))
        with patch.dict(os.environ, {ClaudeCode.PLUGIN_ROOT_ENV: str(plugin)}):
            self.assertEqual([agent.NAME for agent in self.loom.agents_for(self.project)], ["claude"])

    def test_without_a_choice_or_an_invoker_every_present_tool_is_wired(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with (
                patch.object(ClaudeCode, "present", return_value=True),
                patch.object(JetBrains, "present", return_value=False),
                patch.object(OpenCode, "present", return_value=False),
            ):
                self.assertEqual([agent.NAME for agent in self.loom.agents_for(self.project)], ["claude"])
