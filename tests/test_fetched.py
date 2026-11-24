from __future__ import annotations

import shutil
from typing import TYPE_CHECKING
from unittest.mock import PropertyMock, patch

from loomwork.agents import ClaudeCode
from loomwork.sources.manifest import Manifest
from tests.fixtures import (
    SOURCE,
    SandboxTestCase,
    leaving_a_mark,
    make_clone,
    make_target_dir,
    times_marked,
)

if TYPE_CHECKING:
    from pathlib import Path


class AddedSourcesTests(SandboxTestCase):
    """A source may build on others: the same [[source]] blocks, meaning 'I build on this' in a source's own file."""

    def setUp(self) -> None:
        super().setUp()
        self.base = make_clone(self.root, "base-rules")
        self.team = make_clone(self.root, "team-rules")
        # local checkouts that were never pushed
        self.enterContext(patch("loomwork.git.origin", return_value=None))
        self.claude = self.loom.agents_named((ClaudeCode.NAME,))
        self.loom.registry.add_config_dir(self.claude_dir, ClaudeCode.NAME)

    def builds_on(self, source: Path, base: Path) -> None:
        (source / Manifest.FILE_NAME).write_text(f'[[source]]\nsource = "{base}"\n')

    def test_adding_a_source_says_where_it_sits(self) -> None:
        self.loom.sources.add(str(self.team))
        self.assertEqual(self.loom.registry.checkout_of(str(self.team)), self.team)

    def test_what_a_source_builds_on_comes_first(self) -> None:
        # broadest first, so the source that declared the dependency wins a shared filename
        self.builds_on(self.team, self.base)
        self.loom.sources.add(str(self.team), pinned_to=(self.claude_dir,))
        self.assertEqual(self.loom.sources.keys_of(self.claude_dir), [str(self.base), str(self.team)])

    def test_a_cycle_is_added_once(self) -> None:
        self.builds_on(self.team, self.base)
        self.builds_on(self.base, self.team)
        self.loom.sources.add(str(self.team), pinned_to=(self.claude_dir,))
        self.assertEqual(sorted(self.loom.sources.keys_of(self.claude_dir)), sorted([str(self.base), str(self.team)]))


class RefreshTests(SandboxTestCase):
    """Every source a sync copies from is updated before it does."""

    def setUp(self) -> None:
        super().setUp()
        for name in ("one", "two"):
            (self.root / name).mkdir()
            self.loom.registry.add_source(f"forge.test/{name}/rules", self.root / name, f"forge.test/{name}/rules")

    def test_a_refresh_updates_every_source_named(self) -> None:
        with patch("loomwork.git.match_remote", side_effect=leaving_a_mark("updated")):
            self.loom.sources.refresh(["forge.test/one/rules", "forge.test/two/rules"])
        self.assertEqual([times_marked(self.root / name, "updated") for name in ("one", "two")], [1, 1])

    def test_two_sources_in_one_repo_update_it_once(self) -> None:
        repo = self.root / "big-repo"
        (repo / ".git").mkdir(parents=True)
        for name in ("agents", "skills-only"):
            (repo / name).mkdir()
            self.loom.registry.add_source(f"forge.test/big/{name}", repo / name, f"forge.test/big/{name}")
        with patch("loomwork.git.match_remote", side_effect=leaving_a_mark("updated")):
            self.loom.sources.refresh(["forge.test/big/agents", "forge.test/big/skills-only"])
        self.assertEqual(times_marked(repo, "updated"), 1)

    def test_a_cloned_source_that_is_gone_says_how_to_fetch_it_again(self) -> None:
        clone = make_clone(self.root, "gone-rules")
        self.loom.registry.add_source(SOURCE, clone, SOURCE)
        shutil.rmtree(clone)
        said = self.stderr_of(lambda: self.loom.sources.refresh([SOURCE]))
        self.assertIn(f"source {SOURCE} is gone", said)
        self.assertIn(f"init --source {SOURCE}", said)
        self.assertNotIn("could not update", said)

    def test_a_checkout_that_is_gone_asks_where_it_lives_now(self) -> None:
        checkout = make_clone(self.root, "my-rules")
        self.loom.registry.add_source(str(checkout), checkout, str(checkout))
        shutil.rmtree(checkout)
        with patch("loomwork.git.pull", return_value=True):
            said = self.stderr_of(lambda: self.loom.sources.refresh([str(checkout)]))
        self.assertIn(f"source {checkout} is gone — point", said)


class DeclaredSourceTests(SandboxTestCase):
    """A target dir naming a source loom lacks is what makes loom fetch it, even beside one it has."""

    def setUp(self) -> None:
        super().setUp()
        self.clone = make_clone(self.root, "acme-rules")
        self.loom.registry.add_source(SOURCE, self.clone, SOURCE)

    def test_a_source_already_added_is_never_fetched(self) -> None:
        target_dir = make_target_dir(self.root)
        with patch("loomwork.sources.source.Source.fetch", side_effect=AssertionError("should not clone")):
            self.loom.sources.add_declared(target_dir)

    def test_an_unknown_source_is_fetched_even_beside_a_known_one(self) -> None:
        target_dir = make_target_dir(self.root, source="forge.test/other/rules")
        fetched = make_clone(self.root, "other-rules")
        with patch("loomwork.sources.source.Source.fetch", return_value=fetched):
            self.loom.sources.add_declared(target_dir)
        self.assertEqual(self.loom.registry.checkout_of("forge.test/other/rules"), fetched)

    def test_a_source_whose_clone_is_gone_is_fetched_again(self) -> None:
        shutil.rmtree(self.clone)
        target_dir = make_target_dir(self.root)
        fetched = make_clone(self.root, "fetched-again")
        with patch("loomwork.sources.source.Source.fetch", return_value=fetched):
            self.loom.sources.add_declared(target_dir)
        self.assertEqual(self.loom.registry.checkout_of(SOURCE), fetched)

    def test_a_checkout_of_a_cloned_repo_replaces_the_clone(self) -> None:
        # one repo named two ways: the target dir names the working copy, loom holds a fetched clone
        checkout = make_clone(self.root, "rules-checkout")
        target_dir = make_target_dir(self.root, source=str(checkout))
        with patch("loomwork.sources.source.LocalSource.key", new_callable=PropertyMock, return_value=SOURCE):
            self.loom.sources.add_declared(target_dir)
        self.assertEqual(self.loom.registry.checkout_of(SOURCE), checkout)

    def test_a_relative_path_counts_from_the_target_dir(self) -> None:
        sibling = make_clone(self.root, "sibling-rules")
        target_dir = make_target_dir(self.root, source="../sibling-rules")
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        with patch("os.getcwd", return_value=str(elsewhere)), patch("loomwork.git.origin", return_value=None):
            self.loom.sources.add_declared(target_dir)
        self.assertEqual(self.loom.registry.checkout_of(str(sibling)), sibling)
