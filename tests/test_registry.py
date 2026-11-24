from __future__ import annotations

import json

from loomwork.agents import ClaudeCode, OpenCode
from tests.fixtures import SOURCE, TEAM_SOURCE, SandboxTestCase


class RegistryTests(SandboxTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.registry = self.loom.registry
        self.work_dir = self.home / ".claude-work"
        self.registry.add_config_dir(self.claude_dir, ClaudeCode.NAME)
        self.target_dir = self.root / "target_dir"
        self.target_dir.mkdir()

    def test_a_fresh_registry_reads_as_empty(self) -> None:
        self.registry.forget()
        self.assertEqual(self.registry.config_dirs(), [])
        self.assertEqual(self.registry.target_dirs, [])

    def test_a_config_dir_is_one_entry_however_its_path_is_written(self) -> None:
        (self.root / "via-link").symlink_to(self.claude_dir.parent)
        self.registry.add_config_dir(self.root / "via-link" / ".claude", OpenCode.NAME)
        self.assertEqual(self.registry.config_dirs(), [self.claude_dir])
        self.assertEqual(self.registry.get_agent_name(self.claude_dir), ClaudeCode.NAME)

    def test_a_target_dir_is_found_from_every_dir_it_is_wired_from(self) -> None:
        self.registry.add_config_dir(self.work_dir, ClaudeCode.NAME)
        self.registry.add_target_dir(self.claude_dir, self.target_dir, [SOURCE])
        self.registry.add_target_dir(self.work_dir, self.target_dir, [SOURCE])
        self.assertEqual(self.registry.config_dirs_of(self.target_dir), [self.claude_dir, self.work_dir])
        self.assertEqual(self.registry.target_dirs, [self.target_dir])

    def test_dropping_a_target_dir_forgets_it_there_however_often_it_is_dropped(self) -> None:
        self.registry.add_target_dir(self.claude_dir, self.target_dir, [])
        self.registry.drop_target_dir(self.claude_dir, self.target_dir)
        self.registry.drop_target_dir(self.claude_dir, self.target_dir)
        self.assertEqual(self.registry.config_dirs_of(self.target_dir), [])

    def test_a_dir_draws_on_what_its_target_dirs_declare_each_once(self) -> None:
        other = self.root / "other"
        other.mkdir()
        self.registry.add_target_dir(self.claude_dir, self.target_dir, [SOURCE])
        self.registry.add_target_dir(self.claude_dir, other, [SOURCE, TEAM_SOURCE])
        self.assertEqual(self.registry.sources_declared_in(self.claude_dir), [SOURCE, TEAM_SOURCE])

    def test_a_source_pinned_again_moves_to_the_end(self) -> None:
        # a later source wins a filename, so the order is what decides a clash
        self.registry.pin_source(self.claude_dir, SOURCE)
        self.registry.pin_source(self.claude_dir, TEAM_SOURCE)
        self.registry.pin_source(self.claude_dir, SOURCE)
        self.assertEqual(self.registry.sources_pinned_to(self.claude_dir), [TEAM_SOURCE, SOURCE])

    def test_a_source_keeps_where_it_sits_how_it_was_declared_and_what_it_builds_on(self) -> None:
        self.registry.add_source(
            SOURCE, self.root / "agent-rules", "git@forge.test:acme/agent-rules.git", [TEAM_SOURCE]
        )
        self.assertEqual(self.registry.checkout_of(SOURCE), self.root / "agent-rules")
        self.assertEqual(self.registry.source_of(SOURCE), "git@forge.test:acme/agent-rules.git")
        self.assertEqual(self.registry.bases_of(SOURCE), [TEAM_SOURCE])

    def test_what_is_owned_is_found_however_the_directory_is_written(self) -> None:
        directory = self.root / "skills"
        directory.mkdir()
        (self.root / "skills-link").symlink_to(directory)
        self.registry.record_owned_in(self.root / "skills-link", ["translate", "translate"])
        self.assertEqual(self.registry.owned_in(directory), ["translate"])

    def test_records_of_directories_that_are_gone_are_dropped(self) -> None:
        gone = self.root / "deleted-target"
        gone.mkdir()
        self.registry.record_owned_in(gone, ["translate"])
        gone.rmdir()
        kept = self.root / "skills"
        kept.mkdir()
        self.registry.record_owned_in(kept, ["translate"])
        self.assertEqual(list(json.loads(self.registry.path.read_text())["owned"]), [str(kept)])

    def test_a_file_from_another_shape_reads_as_empty(self) -> None:
        # whatever wrote it, loom must start rather than raise on a key it does not know
        self.registry.path.write_text('{"version": 1, "source": {"path": "/somewhere"}, "namespace": "acme"}')
        self.assertEqual(self.registry.config_dirs(), [])
        self.assertEqual(self.registry.source_keys, [])
