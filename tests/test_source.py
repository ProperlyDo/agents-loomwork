from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

from loomwork.errors import LoomError
from loomwork.sources.catalog import Catalog
from loomwork.sources.repo_address import RepoAddress
from loomwork.sources.source import Source
from tests.fixtures import SandboxTestCase, leaving_a_mark, times_marked

if TYPE_CHECKING:
    from pathlib import Path


def make_checkout(root: Path, name: str) -> Path:
    """A directory that reads as the root of a git repo."""
    checkout = root / name
    (checkout / ".git").mkdir(parents=True)
    return checkout


class SourceNamingTests(SandboxTestCase):
    """What a rules source can say about itself: the name to file it under, and the location a declaration carries."""

    def test_a_checkout_is_the_repo_its_remote_names(self) -> None:
        checkout = make_checkout(self.root, "named-rules")
        with patch("loomwork.git.origin", return_value="git@forge.test:Acme/agent-rules"):
            self.assertEqual(Source.of(str(checkout)).key, "forge.test/Acme/agent-rules")

    def test_an_ssh_url_remote_names_the_same_repo(self) -> None:
        checkout = make_checkout(self.root, "ssh-rules")
        with patch("loomwork.git.origin", return_value="ssh://git@forge.test/Acme/agent-rules"):
            self.assertEqual(Source.of(str(checkout)).key, "forge.test/Acme/agent-rules")

    def test_rules_in_a_subdirectory_keep_it_in_the_name(self) -> None:
        checkout = make_checkout(self.root, "big-repo")
        (checkout / "agents").mkdir()
        with patch("loomwork.git.origin", return_value="git@forge.test:group/docker-common"):
            self.assertEqual(Source.of(str(checkout / "agents")).key, "forge.test/group/docker-common/agents")

    def test_a_checkout_without_an_origin_is_its_path(self) -> None:
        # a rules repo that was never pushed can still be declared, by the path it sits at
        checkout = make_checkout(self.root, "unpushed-rules")
        with patch("loomwork.git.origin", return_value=None):
            self.assertIsNone(RepoAddress.of_checkout(checkout))
            self.assertEqual(Source.of(str(checkout)).key, str(checkout))


class ClonesTestCase(SandboxTestCase):
    """Loom's own clones, under a sources dir of the test's own."""

    def setUp(self) -> None:
        super().setUp()
        self.clones = self.root / "sources"
        self.enterContext(patch("loomwork.paths.SOURCES_DIR", self.clones))


class ClonePathTests(ClonesTestCase):
    """Two hosts can carry the same owner and repo, and they are not the same rules."""

    def test_the_host_decides_where_a_clone_lands(self) -> None:
        asked: list[Path] = []

        def refuse(url: str, into: Path) -> bool:  # noqa: ARG001
            asked.append(into)
            return False

        with patch("loomwork.git.clone", side_effect=refuse):
            for host in ("forge.test", "other.test"):
                with self.assertRaises(LoomError):
                    Source.of(f"{host}/acme/rules").fetch()
        self.assertEqual(len(set(asked)), 2)

    def test_a_clone_without_the_named_folder_says_so(self) -> None:
        def clone_without_it(url: str, into: Path) -> bool:  # noqa: ARG001
            (into / "rules").mkdir(parents=True)
            return True

        with patch("loomwork.git.clone", side_effect=clone_without_it), self.assertRaises(LoomError) as refused:
            Source.of("forge.test/acme/rules/agents").fetch()
        self.assertEqual(refused.exception.code, "subdirectory_missing")
        self.assertIn("names agents/, which the clone does not have", str(refused.exception))

    def test_a_failed_clone_leaves_nothing_to_be_taken_for_one(self) -> None:
        def half_clone(url: str, into: Path) -> bool:  # noqa: ARG001
            (into / "rules").mkdir(parents=True)
            return False

        with patch("loomwork.git.clone", side_effect=half_clone), self.assertRaises(LoomError):
            Source.of("forge.test/acme/rules").fetch()
        self.assertEqual(list((self.clones / "forge.test" / "acme").iterdir()), [])


class UpdateTests(ClonesTestCase):
    """A clone of ours takes whatever its remote has; a checkout of yours only fast-forwards."""

    def setUp(self) -> None:
        super().setUp()
        self.clone = self.clones / "forge.test" / "acme" / "rules"
        (self.clone / "rules").mkdir(parents=True)

    def update_with_marks(self, source: Source, checkout: Path) -> None:
        with (
            patch("loomwork.git.match_remote", side_effect=leaving_a_mark("matched")),
            patch("loomwork.git.pull", side_effect=leaving_a_mark("pulled")),
        ):
            source.update(checkout)

    def test_a_source_named_by_its_repo_matches_its_remote(self) -> None:
        self.update_with_marks(Source.of("forge.test/acme/rules"), self.clone)
        self.assertEqual((times_marked(self.clone, "matched"), times_marked(self.clone, "pulled")), (1, 0))

    def test_a_checkout_of_yours_only_pulls(self) -> None:
        checkout = make_checkout(self.root, "my-rules")
        self.update_with_marks(Source.of(str(checkout)), checkout)
        self.assertEqual((times_marked(checkout, "matched"), times_marked(checkout, "pulled")), (0, 1))

    def test_an_existing_clone_is_updated_when_fetched(self) -> None:
        with patch("loomwork.git.match_remote", side_effect=leaving_a_mark("matched")):
            self.assertEqual(Source.of("forge.test/acme/rules").fetch(), self.clone)
        self.assertEqual(times_marked(self.clone, "matched"), 1)

    def test_a_clone_that_cannot_update_is_used_as_it_stands(self) -> None:
        with patch("loomwork.git.match_remote", return_value=False):
            said = self.stderr_of(lambda: self.assertEqual(Source.of("forge.test/acme/rules").fetch(), self.clone))
        self.assertIn("could not update forge.test/acme/rules", said)


class SourceRecognitionTests(SandboxTestCase):
    """What counts as a rules repo: the rules, not the universal layer that may sit beside them."""

    def test_a_repo_of_rules_alone_is_a_source(self) -> None:
        bare = self.root / "rules-only"
        (bare / "rules").mkdir(parents=True)
        self.assertTrue(Catalog.has_rules_or_skills(bare))
        self.assertEqual(Source.of(str(bare)).fetch(), bare)

    def test_a_repo_of_skills_alone_is_a_source(self) -> None:
        # a third-party skills repo is added like any other source, with nothing to declare but skills
        skills_only = self.root / "skills-only"
        (skills_only / "skills" / "spec-writer").mkdir(parents=True)
        self.assertTrue(Catalog.has_rules_or_skills(skills_only))
        self.assertEqual(Source.of(str(skills_only)).fetch(), skills_only)

    def test_a_path_that_is_not_there_is_never_read_as_a_repo(self) -> None:
        with (
            patch("loomwork.git.clone", side_effect=AssertionError("should not clone")),
            self.assertRaises(LoomError) as refused,
        ):
            Source.of(str(self.root / "no-such-rules")).fetch()
        self.assertEqual(refused.exception.code, "no_such_directory")

    def test_a_universal_layer_alone_is_not(self) -> None:
        pretender = self.root / "layer-only"
        pretender.mkdir()
        (pretender / "AGENTS.md").write_text("# Agent Instructions\n")
        self.assertFalse(Catalog.has_rules_or_skills(pretender))
        with self.assertRaises(LoomError):
            Source.of(str(pretender)).fetch()
