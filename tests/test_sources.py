from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import patch

from loomwork import git, sources
from loomwork.declaration import Manifest
from loomwork.sources import Catalog, RepoAddress
from tests.fixtures import SandboxTestCase, make_clone


def make_checkout(root: Path, name: str) -> Path:
    """A directory that reads as the root of a git repo."""
    checkout = root / name
    (checkout / ".git").mkdir(parents=True)
    return checkout


class SourceNamingTests(SandboxTestCase):
    """What a rules source can say about itself: the name to file it under, and the spelling a declaration carries."""

    def test_a_checkout_is_the_repo_its_remote_names(self) -> None:
        checkout = make_checkout(self.root, "named-rules")
        with patch("loomwork.git.origin", return_value="git@forge.test:Acme/agent-rules"):
            self.assertEqual(sources.identity(str(checkout)), "forge.test/Acme/agent-rules")

    def test_an_ssh_url_remote_names_the_same_repo(self) -> None:
        checkout = make_checkout(self.root, "ssh-rules")
        with patch("loomwork.git.origin", return_value="ssh://git@forge.test/Acme/agent-rules"):
            self.assertEqual(sources.identity(str(checkout)), "forge.test/Acme/agent-rules")

    def test_rules_in_a_subdirectory_keep_it_in_the_name(self) -> None:
        checkout = make_checkout(self.root, "big-repo")
        (checkout / "agents").mkdir()
        with patch("loomwork.git.origin", return_value="git@forge.test:group/docker-common"):
            self.assertEqual(sources.identity(str(checkout / "agents")), "forge.test/group/docker-common/agents")

    def test_a_checkout_without_an_origin_is_its_path(self) -> None:
        # a rules repo that was never pushed can still be declared, by the path it sits at
        checkout = make_checkout(self.root, "unpushed-rules")
        with patch("loomwork.git.origin", return_value=None):
            self.assertIsNone(sources.checkout_address(checkout))
            self.assertEqual(sources.identity(str(checkout)), str(checkout))


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
                with self.assertRaises(SystemExit):
                    sources.fetch(f"{host}/acme/rules")
        self.assertEqual(len(set(asked)), 2)

    def test_a_clone_without_the_named_folder_says_so(self) -> None:
        def clone_without_it(url: str, into: Path) -> bool:  # noqa: ARG001
            (into / "rules").mkdir(parents=True)
            return True

        def fetch_the_subfolder() -> None:
            with self.assertRaises(SystemExit):
                sources.fetch("forge.test/acme/rules/agents")

        with patch("loomwork.git.clone", side_effect=clone_without_it):
            said = self.stderr_of(fetch_the_subfolder)
        self.assertIn("names agents/, which the clone does not have", said)

    def test_a_failed_clone_leaves_nothing_to_be_taken_for_one(self) -> None:
        def half_clone(url: str, into: Path) -> bool:  # noqa: ARG001
            (into / "rules").mkdir(parents=True)
            return False

        with patch("loomwork.git.clone", side_effect=half_clone), self.assertRaises(SystemExit):
            sources.fetch("forge.test/acme/rules")
        self.assertEqual(list((self.clones / "forge.test" / "acme").iterdir()), [])


class UpdateTests(ClonesTestCase):
    """A clone of ours takes whatever its remote has; a checkout of yours only fast-forwards."""

    def setUp(self) -> None:
        super().setUp()
        self.clone = self.clones / "forge.test" / "acme" / "rules"
        (self.clone / "rules").mkdir(parents=True)

    def test_a_clone_of_ours_matches_its_remote(self) -> None:
        with patch("loomwork.git.match_remote", return_value=True) as matched, patch("loomwork.git.pull") as pulled:
            sources.update(self.clone)
        matched.assert_called_once_with(self.clone)
        pulled.assert_not_called()

    def test_nothing_is_reset_when_the_fetch_fails(self) -> None:
        with patch("loomwork.git.run", return_value=None) as ran:
            self.assertFalse(git.match_remote(self.clone))
        self.assertEqual(ran.call_count, 1)

    def test_a_checkout_of_yours_only_pulls(self) -> None:
        checkout = make_checkout(self.root, "my-rules")
        with patch("loomwork.git.pull", return_value=True) as pulled, patch("loomwork.git.match_remote") as matched:
            sources.update(checkout)
        pulled.assert_called_once_with(checkout)
        matched.assert_not_called()

    def test_an_existing_clone_is_updated_when_fetched(self) -> None:
        with patch("loomwork.git.match_remote", return_value=True) as matched:
            self.assertEqual(sources.fetch("forge.test/acme/rules"), self.clone)
        matched.assert_called_once_with(self.clone)

    def test_a_clone_that_cannot_update_is_used_as_it_stands(self) -> None:
        with patch("loomwork.git.match_remote", return_value=False):
            said = self.stderr_of(lambda: self.assertEqual(sources.fetch("forge.test/acme/rules"), self.clone))
        self.assertIn("could not update forge.test/acme/rules", said)


class SourceRecognitionTests(SandboxTestCase):
    """What counts as a rules repo: the rules, not the universal layer that may sit beside them."""

    def test_a_repo_of_rules_alone_is_a_source(self) -> None:
        bare = self.root / "rules-only"
        (bare / "rules").mkdir(parents=True)
        self.assertTrue(sources.is_source(bare))
        self.assertEqual(sources.fetch(str(bare)), bare)

    def test_a_repo_of_skills_alone_is_a_source(self) -> None:
        # a third-party skills repo is added like any other source, with nothing to declare but skills
        skills_only = self.root / "skills-only"
        (skills_only / "skills" / "spec-writer").mkdir(parents=True)
        self.assertTrue(sources.is_source(skills_only))
        self.assertEqual(sources.fetch(str(skills_only)), skills_only)

    def test_a_path_that_is_not_there_is_never_read_as_a_repo(self) -> None:
        def fetch_the_missing_path() -> None:
            with self.assertRaises(SystemExit):
                sources.fetch(str(self.root / "no-such-rules"))

        with patch("loomwork.git.clone", side_effect=AssertionError("should not clone")):
            said = self.stderr_of(fetch_the_missing_path)
        self.assertIn("no such directory", said)

    def test_a_universal_layer_alone_is_not(self) -> None:
        pretender = self.root / "layer-only"
        pretender.mkdir()
        (pretender / "AGENTS.md").write_text("# Agent Instructions\n")
        self.assertFalse(sources.is_source(pretender))
        with self.assertRaises(SystemExit):
            sources.fetch(str(pretender))


class SourceSpellingTests(SandboxTestCase):
    """However a clone url was copied, it names the same repo."""

    def test_every_spelling_reduces_to_host_owner_repo(self) -> None:
        for spelling in (
            "forge.test/acme/agent-rules",
            "https://forge.test/acme/agent-rules",
            "git@forge.test:acme/agent-rules.git",
            "ssh://git@forge.test/acme/agent-rules/",
            "ssh://git@forge.test:2222/acme/agent-rules.git",
            "https://user:token@forge.test/acme/agent-rules",
        ):
            self.assertEqual(
                RepoAddress.from_spelling(spelling), RepoAddress("forge.test", "acme", "agent-rules"), spelling
            )

    def test_a_subdirectory_survives_the_scheme(self) -> None:
        self.assertEqual(
            RepoAddress.from_spelling("ssh://git@forge.test/group/repo/agents"),
            RepoAddress("forge.test", "group", "repo", "agents"),
        )

    def test_something_that_names_no_repo_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            RepoAddress.from_spelling("nonsense")


class CatalogTests(SandboxTestCase):
    """What a set of sources defines, what a project may choose from it, and what it hands out anyway."""

    def setUp(self) -> None:
        super().setUp()
        self.clone = make_clone(self.root)

    def test_a_global_rule_is_defined_but_not_offered(self) -> None:
        # git.md reaches every project, declared or not, so choosing it would mean nothing
        catalog = Catalog.of(self.clone)
        self.assertEqual(catalog.global_rules, ("git",))
        self.assertNotIn("git", catalog.offered_rules)
        self.assertIn("python", catalog.offered_rules)

    def test_a_later_source_adds_its_own_rules(self) -> None:
        team = make_clone(self.root, "team-rules")
        (team / "rules" / "team.md").write_text("# Team\n")
        defined = {rule.name for rule in Catalog.of(self.clone, team).rules.values()}
        self.assertIn("team.md", defined)
        self.assertIn("django.md", defined)

    def test_a_folder_without_its_skill_file_is_not_defined(self) -> None:
        (self.clone / "skills" / "half-written").mkdir()
        self.assertNotIn("half-written", Catalog.of(self.clone).skills)

    def test_a_source_without_skills_defines_none(self) -> None:
        bare = make_clone(self.root, "rules-only")
        shutil.rmtree(bare / "skills")
        self.assertEqual(Catalog.of(bare).skills, {})

    def test_a_source_without_rules_defines_none(self) -> None:
        skills_only = self.root / "skills-only"
        (skills_only / "skills" / "spec-writer").mkdir(parents=True)
        (skills_only / "skills" / "spec-writer" / "SKILL.md").write_text("---\nname: spec-writer\n---\n")
        self.assertEqual(Catalog.of(skills_only).rules, {})

    def test_a_directory_that_is_not_there_defines_nothing(self) -> None:
        nothing = Catalog.of(self.root / "nothing")
        self.assertEqual((nothing.rules, nothing.skills, nothing.global_skills), ({}, {}, ()))

    def test_only_skills_marked_global_count_as_global(self) -> None:
        everywhere = self.clone / "skills" / "everywhere"
        everywhere.mkdir(parents=True)
        (everywhere / "SKILL.md").write_text("---\nname: everywhere\n---\n")
        (self.clone / Manifest.FILE_NAME).write_text('[global]\nrules = ["git"]\nskills = ["everywhere"]\n')
        self.assertEqual(Catalog.of(self.clone).global_skills, ("everywhere",))

    def test_a_global_name_the_source_does_not_ship_is_skipped(self) -> None:
        (self.clone / Manifest.FILE_NAME).write_text('[global]\nskills = ["missing"]\n')
        self.assertEqual(Catalog.of(self.clone).global_skills, ())

    def test_a_repo_not_made_for_loom_keeps_its_agents_md_to_itself(self) -> None:
        skills_repo = self.root / "skills-repo"
        (skills_repo / "skills").mkdir(parents=True)
        (skills_repo / "AGENTS.md").write_text("# Contributor instructions\n")
        self.assertIn("# Agent Instructions", Catalog.of(self.clone, skills_repo).agents_md.read_text())

    def test_each_source_reads_its_own_universal_layer(self) -> None:
        other = make_clone(self.root, "other-rules")
        (other / "AGENTS.md").write_text("# Other Instructions\n")
        self.assertIn("# Agent Instructions", Catalog.of(self.clone).agents_md.read_text())
        self.assertIn("# Other Instructions", Catalog.of(other).agents_md.read_text())

    def test_a_source_without_its_agents_md_hands_out_none(self) -> None:
        (self.clone / "AGENTS.md").unlink()
        self.assertIsNone(Catalog.of(self.clone).agents_md)
