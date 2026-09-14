from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from installer.agents import ClaudeCode, JetBrains, OpenCode
from installer.installation import Installation

STACK_RULE = "# Python\n"
NEUTRAL_RULE = "---\nreach: global\n---\n\n# Git\n"


def make_clone(root: Path, name: str = "agents-config") -> Path:
    """A stand-in for a checkout of this repo: the universal layer plus one stack and one neutral rule."""
    clone = root / name
    (clone / "rules").mkdir(parents=True)
    (clone / "AGENTS.md").write_text("# Agent Instructions\n")
    (clone / "rules" / "python.md").write_text(STACK_RULE)
    (clone / "rules" / "django.md").write_text(STACK_RULE)
    (clone / "rules" / "git.md").write_text(NEUTRAL_RULE)
    return clone


def make_project(root: Path, stacks: str | None = "stacks: [python]") -> Path:
    project = root / "project"
    project.mkdir()
    declaration = f"---\n{stacks}\n---\n\n# Project\n" if stacks is not None else "# Project\n"
    (project / "AGENTS.md").write_text(declaration)
    return project


class InstallationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        # resolved, because ownership follows links to their end — /var and /private/var must not differ here
        self.root = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(lambda: __import__("shutil").rmtree(self.root, ignore_errors=True))
        self.clone = make_clone(self.root)
        self.installation = Installation(
            namespace="acme",
            agents_dir=self.root / "home" / ".agents",
            repo_dir=self.clone,
        )
        # wiring announces new links — only the tests that assert on it want that on the terminal
        muted_stdout = patch("sys.stdout", new_callable=io.StringIO)
        muted_stdout.start()
        self.addCleanup(muted_stdout.stop)

    def stderr_of(self, action) -> str:
        captured = io.StringIO()
        with redirect_stderr(captured):
            action()
        return captured.getvalue()

    def stdout_of(self, action) -> str:
        captured = io.StringIO()
        with redirect_stdout(captured):
            action()
        return captured.getvalue()


class OwnershipTests(InstallationTestCase):
    def test_link_into_the_clone_is_ours(self) -> None:
        link = self.root / "git.md"
        link.symlink_to(self.clone / "rules" / "git.md")
        self.assertTrue(self.installation.owned(link))

    def test_link_through_the_agents_dir_is_ours(self) -> None:
        self.installation.populate_agents_dir()
        link = self.root / "bridged.md"
        link.symlink_to(self.installation.rules_dir / "git.md")
        self.assertTrue(self.installation.owned(link))

    def test_another_installations_link_is_foreign(self) -> None:
        other = Installation(
            namespace="other",
            agents_dir=self.installation.agents_dir,
            repo_dir=make_clone(self.root, "other-config"),
        )
        other.populate_agents_dir()
        link = self.root / "theirs.md"
        link.symlink_to(other.rules_dir / "git.md")
        self.assertFalse(self.installation.owned(link))

    def test_relative_link_from_another_tool_is_foreign(self) -> None:
        # the skills CLI links its installs relatively; pruning those would delete a neighbour's work
        (self.root / "skills").mkdir()
        (self.root / "skills" / "find-skills").mkdir()
        link = self.root / "find-skills"
        link.symlink_to("skills/find-skills")
        self.assertFalse(self.installation.owned(link))

    def test_real_file_is_never_ours(self) -> None:
        rule = self.root / "hand-written.md"
        rule.write_text("mine\n")
        self.assertFalse(self.installation.owned(rule))

    def test_a_copy_we_wrote_is_ours(self) -> None:
        copy = self.root / "python.md"
        self.installation.copy_rule(self.clone / "rules" / "python.md", copy)
        self.assertFalse(copy.is_symlink())
        self.assertTrue(self.installation.owned(copy))


class ReconcileTests(InstallationTestCase):
    def test_links_sources_and_prunes_what_left(self) -> None:
        into = self.root / "dest"
        rules = self.installation.shipped_rule_files()
        self.installation.reconcile(self.installation.by_name(rules), into)
        self.assertEqual({entry.name for entry in into.iterdir()}, {"python.md", "django.md", "git.md"})

        self.installation.reconcile(self.installation.by_name(rules[:1]), into)
        self.assertEqual({entry.name for entry in into.iterdir()}, {rules[0].name})

    def test_foreign_entries_survive(self) -> None:
        into = self.root / "dest"
        into.mkdir()
        (into / "theirs.md").write_text("not ours\n")
        self.installation.reconcile(self.installation.by_name(self.installation.shipped_rule_files()), into)
        self.installation.reconcile({}, into)
        self.assertTrue((into / "theirs.md").is_file())

    def test_a_name_taken_by_a_foreign_file_is_skipped_with_a_warning(self) -> None:
        into = self.root / "dest"
        into.mkdir()
        (into / "git.md").write_text("hand-made\n")
        links = self.installation.by_name(self.installation.shipped_rule_files())
        warning = self.stderr_of(lambda: self.installation.reconcile(links, into))
        self.assertIn("not ours", warning)
        self.assertEqual((into / "git.md").read_text(), "hand-made\n")


class WireProjectTests(InstallationTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.installation.populate_agents_dir()

    def container_of(self, project: Path) -> Path:
        return project / ".agents" / "rules" / "acme"

    def test_declared_stacks_and_the_project_file_are_linked(self) -> None:
        project = make_project(self.root)
        self.installation.wire_project(project, ())
        container = self.container_of(project)
        self.assertEqual({entry.name for entry in container.iterdir()}, {"python.md", "project.md"})
        self.assertEqual((container / "project.md").resolve(), project / "AGENTS.md")

    def test_unknown_stack_warns_and_is_skipped(self) -> None:
        project = make_project(self.root, "stacks: [python, cobol]")
        warning = self.stderr_of(lambda: self.installation.wire_project(project, ()))
        self.assertIn("cobol", warning)
        self.assertEqual({entry.name for entry in self.container_of(project).iterdir()}, {"python.md", "project.md"})

    def test_dropping_the_declaration_unwires(self) -> None:
        project = make_project(self.root)
        self.installation.wire_project(project, ())
        (project / "AGENTS.md").write_text("# Project\n")
        self.installation.wire_project(project, ())
        self.assertFalse((project / ".agents" / "rules").exists())

    def test_unparsable_declaration_warns_before_unwiring(self) -> None:
        project = make_project(self.root, "stacks: python, django")
        warning = self.stderr_of(lambda: self.installation.wire_project(project, ()))
        self.assertIn("stacks:", warning)

    def test_a_first_pass_announces_the_new_links_and_later_ones_stay_silent(self) -> None:
        project = make_project(self.root)
        first = self.stdout_of(lambda: self.installation.wire_project(project, ()))
        second = self.stdout_of(lambda: self.installation.wire_project(project, ()))
        self.assertIn("restart the session", first)
        self.assertEqual(second, "")

    def test_a_stack_added_later_announces_itself(self) -> None:
        project = make_project(self.root)
        self.installation.wire_project(project, ())
        (project / "AGENTS.md").write_text("---\nstacks: [python, django]\n---\n")
        self.assertIn("restart the session", self.stdout_of(lambda: self.installation.wire_project(project, ())))

    def test_stack_rules_are_copied_not_linked(self) -> None:
        # a link here resolves outside the project, which Claude gates behind an approval nothing raises
        project = make_project(self.root)
        self.installation.wire_project(project, ())
        copy = self.container_of(project) / "python.md"
        self.assertFalse(copy.is_symlink())
        self.assertIn("# Python", copy.read_text())

    def test_a_container_from_the_link_era_is_rewritten_in_place(self) -> None:
        project = make_project(self.root)
        container = self.container_of(project)
        container.mkdir(parents=True)
        (container / "python.md").symlink_to(self.installation.rules_dir / "python.md")
        self.installation.wire_project(project, ())
        self.assertFalse((container / "python.md").is_symlink())
        # writing through the stale link would have edited the clone itself
        self.assertEqual((self.clone / "rules" / "python.md").read_text(), STACK_RULE)

    def test_a_foreign_file_in_the_container_is_skipped_with_a_warning(self) -> None:
        project = make_project(self.root)
        container = self.container_of(project)
        container.mkdir(parents=True)
        (container / "python.md").write_text("hand-made\n")
        warning = self.stderr_of(lambda: self.installation.wire_project(project, ()))
        self.assertIn("not ours", warning)
        self.assertEqual((container / "python.md").read_text(), "hand-made\n")

    def test_a_dropped_stack_leaves_no_zombie_link(self) -> None:
        project = make_project(self.root, "stacks: [python, django]")
        self.installation.wire_project(project, ())
        (project / "AGENTS.md").write_text("---\nstacks: [python]\n---\n")
        self.installation.wire_project(project, ())
        self.assertEqual({entry.name for entry in self.container_of(project).iterdir()}, {"python.md", "project.md"})


class ClaudeCodeTests(InstallationTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.config_dir = self.root / "home" / ".claude"
        self.config_dir.mkdir(parents=True)
        self.env = patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(self.config_dir)})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.agent = ClaudeCode()
        self.installation.populate_agents_dir()

    def test_only_rules_marked_global_bridge_globally(self) -> None:
        self.agent.bridge(self.installation)
        bridged = self.config_dir / "rules" / "acme"
        self.assertEqual({entry.name for entry in bridged.iterdir()}, {"git.md"})
        self.assertEqual((self.config_dir / "CLAUDE.md").resolve(), self.clone / "AGENTS.md")

    def test_skills_are_left_to_the_skills_cli(self) -> None:
        (self.config_dir / "skills").mkdir()
        (self.config_dir / "skills" / "theirs").mkdir()
        self.agent.bridge(self.installation)
        self.assertTrue((self.config_dir / "skills" / "theirs").is_dir())

    def test_register_keeps_foreign_hooks_and_converges_on_one_entry(self) -> None:
        settings = {"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "echo theirs"}]}]}}
        self.agent.settings_file.write_text(json.dumps(settings))
        self.agent.register(self.installation)
        self.agent.register(self.installation)
        entries = json.loads(self.agent.settings_file.read_text())["hooks"]["SessionStart"]
        commands = [hook["command"] for entry in entries for hook in entry["hooks"]]
        self.assertEqual(commands.count("echo theirs"), 1)
        self.assertEqual(len([command for command in commands if "install.py sync" in command]), 1)

    def test_unregister_removes_only_our_hook(self) -> None:
        settings = {"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "echo theirs"}]}]}}
        self.agent.settings_file.write_text(json.dumps(settings))
        self.agent.register(self.installation)
        self.agent.unregister(self.installation)
        entries = json.loads(self.agent.settings_file.read_text())["hooks"]["SessionStart"]
        commands = [hook["command"] for entry in entries for hook in entry["hooks"]]
        self.assertEqual(commands, ["echo theirs"])

    def test_project_rules_link_is_wholesale(self) -> None:
        project = make_project(self.root)
        self.installation.wire_project(project, (self.agent,))
        self.assertEqual(os.readlink(project / ".claude" / "rules"), Installation.PROJECT_RULES_TARGET)


class JetBrainsTests(InstallationTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.agent = JetBrains()
        self.installation.populate_agents_dir()

    def test_project_set_carries_every_layer(self) -> None:
        project = make_project(self.root)
        self.agent.bridge_project(self.installation, project)
        linked = {entry.name for entry in (project / ".aiassistant" / "rules").iterdir()}
        self.assertEqual(linked, {"AGENTS.md", "git.md", "python.md", "project.md"})

    def test_the_project_file_survives_a_second_pass(self) -> None:
        project = make_project(self.root)
        self.agent.bridge_project(self.installation, project)
        self.agent.bridge_project(self.installation, project)
        project_link = project / ".aiassistant" / "rules" / "project.md"
        self.assertEqual(project_link.resolve(), project / "AGENTS.md")

    def test_unbridge_removes_the_whole_tree(self) -> None:
        project = make_project(self.root)
        self.agent.bridge_project(self.installation, project)
        self.agent.unbridge_project(self.installation, project)
        self.assertFalse((project / ".aiassistant").exists())


class OpenCodeTests(InstallationTestCase):
    def test_the_global_agents_file_is_the_whole_bridge(self) -> None:
        config_dir = self.root / "home" / ".config" / "opencode"
        config_dir.mkdir(parents=True)
        with patch.dict(os.environ, {"OPENCODE_CONFIG_DIR": str(config_dir)}):
            self.installation.populate_agents_dir()
            agent = OpenCode()
            agent.bridge(self.installation)
            self.assertEqual((config_dir / "AGENTS.md").resolve(), self.clone / "AGENTS.md")
            agent.unbridge(self.installation)
            self.assertFalse((config_dir / "AGENTS.md").is_symlink())


if __name__ == "__main__":
    unittest.main()
