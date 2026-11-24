from __future__ import annotations

from loomwork import paths
from loomwork.agents import ClaudeCode
from loomwork.targets.declaration import Declaration
from tests.fixtures import SOURCE, WiredTargetDirTestCase, declare


class SyncTests(WiredTargetDirTestCase):
    """What a sync says and keeps doing once a target dir is wired."""

    def test_a_sync_that_changed_something_asks_for_one_restart(self) -> None:
        said = self.stdout_of(lambda: self.loom.sync(self.target_dir, self.claude))
        self.assertEqual(said.count("restart any open session"), 1)

    def test_a_sync_that_changed_nothing_asks_for_no_restart(self) -> None:
        self.loom.sync(self.target_dir, self.claude)
        self.assertNotIn("restart", self.stdout_of(lambda: self.loom.sync(self.target_dir, self.claude)))

    def test_an_opted_out_target_dir_loses_the_links_of_an_agent_wired_from_two_dirs(self) -> None:
        self.loom._add_target_dir(self.target_dir, (self.claude,))
        work_dir = self.home / ".claude-work"
        self.loom.registry.add_config_dir(work_dir, ClaudeCode.NAME)
        self.loom.registry.add_target_dir(work_dir, self.target_dir, [SOURCE])
        (self.target_dir / Declaration.FILE_NAME).unlink()
        self.stderr_of(lambda: self.loom.sync(self.target_dir))
        self.assertFalse((self.target_dir / ".claude" / "rules" / "loom").is_symlink())
        self.assertEqual(self.loom.registry.target_dirs, [])

    def test_syncing_every_target_dir_goes_on_past_a_broken_one(self) -> None:
        self.loom._add_target_dir(self.target_dir, (self.claude,))
        broken = self.root / "broken"
        broken.mkdir()
        declare(broken, ("python",))
        self.loom._add_target_dir(broken, (self.claude,))
        (broken / Declaration.FILE_NAME).write_text("source = \n")
        paths.target_rules_dir(self.target_dir).joinpath("python.md").unlink()
        said = self.stderr_of(self.loom.sync_all)
        self.assertIn(str(broken), said)
        self.assertTrue((paths.target_rules_dir(self.target_dir) / "python.md").is_file())
