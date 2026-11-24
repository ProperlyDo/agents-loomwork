from __future__ import annotations

from loomwork.targets.gitignore import Gitignore
from tests.fixtures import SandboxTestCase


class GitignoreTests(SandboxTestCase):
    """What init offers to add to a target dir's .gitignore."""

    def setUp(self) -> None:
        super().setUp()
        self.target_dir = self.root / "target_dir"

    def test_gitignore_covers_every_agents_folders(self) -> None:
        self.assertEqual(Gitignore(self.target_dir, self.loom.agents)._ours, (".agents/", ".claude/", ".opencode/"))

    def test_a_file_inside_a_folder_does_not_cover_the_folder(self) -> None:
        self.target_dir.mkdir()
        (self.target_dir / ".gitignore").write_text(".claude/settings.local.json\n/.agents\n")
        self.assertEqual(Gitignore(self.target_dir, self.loom.agents).unignored(), [".claude/", ".opencode/"])
