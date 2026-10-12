from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from loomwork.agents import ClaudeCode, JetBrains, OpenCode
from loomwork.declaration import Declaration
from loomwork.installation import Installation

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


def make_project(root: Path, rules: tuple[str, ...] = ("python",), namespace: str = "acme") -> Path:
    project = root / "project"
    project.mkdir()
    (project / "AGENTS.md").write_text("# Project\n")
    declare(project, rules, namespace)
    return project


def declare(project: Path, rules: tuple[str, ...], namespace: str = "acme") -> None:
    """The committed opt-in: where the rules come from, whose they are, and which of them this project wants."""
    listed = ", ".join(f'"{name}"' for name in rules)
    (project / Declaration.FILE_NAME).write_text(
        f'source = "github.com/acme/agent-rules"\nnamespace = "{namespace}"\nrules = [{listed}]\n'
    )


def sandboxed_config_dirs(root: Path):
    """Every tool's config dir inside the test's own directory — without this, a bridge reaches the real ~/.claude."""
    return patch.dict(
        os.environ,
        {
            "CLAUDE_CONFIG_DIR": str(root / "home" / ".claude"),
            "OPENCODE_CONFIG_DIR": str(root / "home" / ".config" / "opencode"),
        },
    )


class InstallationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        # resolved, because ownership follows links to their end — /var and /private/var must not differ here
        self.root = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(lambda: __import__("shutil").rmtree(self.root, ignore_errors=True))
        self.clone = make_clone(self.root)
        self.installation = Installation(
            namespace="acme",
            agents_dir=self.root / "home" / ".agents",
            source=self.clone,
        )
        sandbox = sandboxed_config_dirs(self.root)
        sandbox.start()
        self.addCleanup(sandbox.stop)
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

    def test_a_staged_rule_is_ours(self) -> None:
        self.installation.populate_agents_dir()
        self.assertTrue(self.installation.owned(self.installation.rules_dir / "git.md"))

    def test_another_installations_link_is_foreign(self) -> None:
        other = Installation(
            namespace="other",
            agents_dir=self.installation.agents_dir,
            source=make_clone(self.root, "other-config"),
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

    def test_a_dangling_link_is_ours_to_replace(self) -> None:
        # a moved source leaves every link of ours pointing nowhere; refusing them would make repair impossible
        link = self.root / "python.md"
        link.symlink_to(self.root / "moved-away" / "rules" / "python.md")
        self.assertTrue(self.installation.owned(link))

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

    def test_only_the_declared_rules_land_in_the_container(self) -> None:
        project = make_project(self.root)
        self.installation.wire_project(project, ())
        self.assertEqual({entry.name for entry in self.container_of(project).iterdir()}, {"python.md"})

    def test_a_project_file_link_from_an_older_install_is_pruned(self) -> None:
        project = make_project(self.root)
        container = self.container_of(project)
        container.mkdir(parents=True)
        (container / "project.md").symlink_to(Installation.PROJECT_MD_TARGET)
        self.installation.wire_project(project, ())
        self.assertEqual({entry.name for entry in container.iterdir()}, {"python.md"})

    def test_unknown_rule_warns_and_is_skipped(self) -> None:
        project = make_project(self.root, ("python", "cobol"))
        warning = self.stderr_of(lambda: self.installation.wire_project(project, ()))
        self.assertIn("cobol", warning)
        self.assertEqual({entry.name for entry in self.container_of(project).iterdir()}, {"python.md"})

    def test_dropping_the_declaration_unwires(self) -> None:
        project = make_project(self.root)
        self.installation.wire_project(project, ())
        (project / Declaration.FILE_NAME).unlink()
        self.installation.wire_project(project, ())
        self.assertFalse((project / ".agents" / "rules").exists())

    def test_a_project_asking_for_another_namespace_is_left_alone(self) -> None:
        # someone else's rules are not ours to wire, and leaving them is not the same as unwiring
        project = make_project(self.root, ("python",), namespace="stranger")
        self.installation.wire_project(project, ())
        self.assertFalse((project / ".agents").exists())

    def test_a_namespace_of_ours_is_wired_even_when_the_declaration_omits_it(self) -> None:
        project = make_project(self.root)
        (project / Declaration.FILE_NAME).write_text('source = "github.com/acme/agent-rules"\nrules = ["python"]\n')
        self.installation.wire_project(project, ())
        self.assertEqual({entry.name for entry in self.container_of(project).iterdir()}, {"python.md"})

    def test_a_first_pass_announces_the_new_links_and_later_ones_stay_silent(self) -> None:
        project = make_project(self.root)
        first = self.stdout_of(lambda: self.installation.wire_project(project, ()))
        second = self.stdout_of(lambda: self.installation.wire_project(project, ()))
        self.assertIn("restart the session", first)
        self.assertEqual(second, "")

    def test_a_rule_added_later_announces_itself(self) -> None:
        project = make_project(self.root)
        self.installation.wire_project(project, ())
        declare(project, ("python", "django"))
        self.assertIn("restart the session", self.stdout_of(lambda: self.installation.wire_project(project, ())))

    def test_replacing_a_link_era_rule_announces_itself(self) -> None:
        # the migration rewrites content the running session never had — the same situation as a new rule
        project = make_project(self.root)
        container = self.container_of(project)
        container.mkdir(parents=True)
        (container / "python.md").symlink_to(self.installation.rules_dir / "python.md")
        self.assertIn("restart the session", self.stdout_of(lambda: self.installation.wire_project(project, ())))

    def test_an_upstream_edit_announces_itself(self) -> None:
        project = make_project(self.root)
        self.installation.wire_project(project, ())
        (self.clone / "rules" / "python.md").write_text(STACK_RULE + "- a rule added upstream\n")
        self.assertIn("restart the session", self.stdout_of(lambda: self.installation.wire(project, ())))

    def test_a_dropped_rule_announces_itself(self) -> None:
        project = make_project(self.root, ("python", "django"))
        self.installation.wire_project(project, ())
        declare(project, ("python",))
        self.assertIn("restart the session", self.stdout_of(lambda: self.installation.wire_project(project, ())))

    def test_rules_are_copied_not_linked(self) -> None:
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

    def test_a_container_from_a_former_name_is_cleared(self) -> None:
        # .claude/rules reaches every namespace dir, so a leftover one keeps loading its rules
        project = make_project(self.root)
        renamed = Installation(
            namespace="acme-new",
            agents_dir=self.installation.agents_dir,
            source=self.clone,
            former_namespaces=("acme",),
        )
        self.installation.wire_project(project, ())
        # a rename moves the machine and the project's declaration together; the old container is what lingers
        declare(project, ("python",), namespace="acme-new")
        renamed.wire_project(project, ())
        containers = {entry.name for entry in (project / ".agents" / "rules").iterdir()}
        self.assertEqual(containers, {"acme-new"})

    def test_another_installations_container_is_left_alone(self) -> None:
        project = make_project(self.root)
        theirs = project / ".agents" / "rules" / "stranger"
        theirs.mkdir(parents=True)
        (theirs / "python.md").write_text("# Theirs\n")
        self.installation.wire_project(project, ())
        self.assertTrue((theirs / "python.md").is_file())

    def test_a_dropped_rule_leaves_no_zombie_copy(self) -> None:
        project = make_project(self.root, ("python", "django"))
        self.installation.wire_project(project, ())
        declare(project, ("python",))
        self.installation.wire_project(project, ())
        self.assertEqual({entry.name for entry in self.container_of(project).iterdir()}, {"python.md"})


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
        self.assertIn("# Agent Instructions", (self.config_dir / "CLAUDE.md").read_text())

    def test_skills_are_left_to_the_skills_cli(self) -> None:
        (self.config_dir / "skills").mkdir()
        (self.config_dir / "skills" / "theirs").mkdir()
        self.agent.bridge(self.installation)
        self.assertTrue((self.config_dir / "skills" / "theirs").is_dir())

    def hooks_in(self, settings_file: Path) -> list[str]:
        entries = json.loads(settings_file.read_text())["hooks"]["SessionStart"]
        return [hook["command"] for entry in entries for hook in entry["hooks"]]

    def test_an_entry_file_from_an_older_version_is_removed_on_the_next_pass(self) -> None:
        # it suppressed the native reading of the project's AGENTS.md, which is why it goes
        project = make_project(self.root)
        entry_file = project / self.agent.ENTRY_FILE
        entry_file.write_text(f"@AGENTS.md\n\n{Installation.COPY_MARKER}\n")
        self.installation.wire_project(project, (self.agent,))
        self.assertFalse(entry_file.exists())

    def test_a_hand_written_entry_file_is_left_alone(self) -> None:
        project = make_project(self.root)
        entry_file = project / self.agent.ENTRY_FILE
        entry_file.write_text("my own notes\n")
        self.installation.wire_project(project, (self.agent,))
        self.assertEqual(entry_file.read_text(), "my own notes\n")

    def test_wiring_writes_no_hook(self) -> None:
        # the plugin declares one SessionStart hook for the machine; a project needs none of its own
        project = make_project(self.root)
        self.installation.wire_project(project, (self.agent,))
        self.assertFalse(self.agent.local_settings_file(project).exists())
        self.assertFalse((self.config_dir / "settings.json").exists())

    def test_wiring_clears_a_hook_an_earlier_version_wrote(self) -> None:
        project = make_project(self.root)
        settings_file = self.agent.local_settings_file(project)
        settings_file.parent.mkdir(parents=True)
        ours = {"type": "command", "command": f"loomwork sync {project}"}
        theirs = {"type": "command", "command": "echo theirs"}
        settings_file.write_text(json.dumps({"hooks": {"SessionStart": [{"hooks": [ours, theirs]}]}}))
        self.installation.wire_project(project, (self.agent,))
        self.assertEqual(self.hooks_in(settings_file), ["echo theirs"])

    def test_unwiring_removes_only_our_hook(self) -> None:
        project = make_project(self.root)
        settings_file = self.agent.local_settings_file(project)
        settings_file.parent.mkdir(parents=True)
        settings_file.write_text(
            json.dumps({"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "echo theirs"}]}]}})
        )
        self.installation.wire_project(project, (self.agent,))
        self.agent.unbridge_project(self.installation, project)
        self.assertEqual(self.hooks_in(settings_file), ["echo theirs"])

    def test_a_machine_hook_from_an_older_install_is_cleared(self) -> None:
        legacy = {
            "hooks": {
                "SessionStart": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": '/somewhere/install.py sync --namespace acme "$CLAUDE_PROJECT_DIR"',
                            },
                            {"type": "command", "command": "echo theirs"},
                        ]
                    }
                ]
            }
        }
        (self.config_dir / "settings.json").write_text(json.dumps(legacy))
        self.agent.forget_machine_hook(self.installation)
        self.assertEqual(self.hooks_in(self.config_dir / "settings.json"), ["echo theirs"])

    def test_project_rules_link_is_wholesale(self) -> None:
        project = make_project(self.root)
        self.installation.wire_project(project, (self.agent,))
        self.assertEqual(str((project / ".claude" / "rules").readlink()), ClaudeCode.PROJECT_RULES_TARGET)


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

    def test_a_project_without_its_own_file_gets_no_project_link(self) -> None:
        project = make_project(self.root)
        (project / "AGENTS.md").unlink()
        self.agent.bridge_project(self.installation, project)
        self.assertFalse((project / ".aiassistant" / "rules" / "project.md").is_symlink())

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
            self.assertIn("# Agent Instructions", (config_dir / "AGENTS.md").read_text())
            agent.unbridge(self.installation)
            self.assertFalse((config_dir / "AGENTS.md").exists())


if __name__ == "__main__":
    unittest.main()


class HookRecognitionTests(InstallationTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.agent = ClaudeCode()

    def test_a_hook_written_under_either_console_script_is_ours(self) -> None:
        for command in ("loom sync /x", "loomwork sync /x", "/opt/homebrew/bin/loom sync /x"):
            self.assertTrue(self.agent.our_hook(self.installation, {"command": command}), command)

    def test_a_foreign_sync_command_is_not_ours(self) -> None:
        self.assertFalse(self.agent.our_hook(self.installation, {"command": "rsync sync /x"}))
        self.assertFalse(self.agent.our_hook(self.installation, {"command": "echo loom sync"}))
