from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from loomwork.installation import Installation
from tests.fixtures import InstallationTestCase


class OwnershipTests(InstallationTestCase):
    def test_a_link_into_its_target_dirs_agents_dir_is_ours_even_dangling(self) -> None:
        # .agents/ may be gone, and a link we laid still has to be ours to remove
        rules_dir = self.root / "target_dir" / ".claude" / "rules"
        rules_dir.mkdir(parents=True)
        (rules_dir / "loom").symlink_to("../../.agents/rules")
        self.assertTrue(self.installation.owns(rules_dir / "loom"))

    def test_a_link_into_another_target_dirs_agents_dir_is_foreign(self) -> None:
        (self.root / "here").mkdir()
        link = self.root / "here" / "python.md"
        link.symlink_to(self.root / "elsewhere" / ".agents" / "rules" / "python.md")
        self.assertFalse(self.installation.owns(link))

    def test_a_link_into_a_source_is_foreign(self) -> None:
        link = self.root / "git.md"
        link.symlink_to(self.clone / "rules" / "git.md")
        self.assertFalse(self.installation.owns(link))

    def test_a_relative_link_from_the_skills_cli_is_foreign(self) -> None:
        # the skills CLI links its installs relatively; clearing those would delete a neighbour's work
        (self.root / "skills" / "find-skills").mkdir(parents=True)
        link = self.root / "find-skills"
        link.symlink_to("skills/find-skills")
        self.assertFalse(self.installation.owns(link))

    def test_a_dangling_link_aiming_elsewhere_is_foreign(self) -> None:
        link = self.root / "python.md"
        link.symlink_to(self.root / "moved-away" / "rules" / "python.md")
        self.assertFalse(self.installation.owns(link))

    def test_real_file_is_never_ours(self) -> None:
        rule = self.root / "hand-written.md"
        rule.write_text("mine\n")
        self.assertFalse(self.installation.owns(rule))

    def test_a_copy_of_a_copy_carries_one_marker(self) -> None:
        first = self.root / "python.md"
        second = self.root / "python-again.md"
        self.installation.place_file(self.clone / "rules" / "python.md", first)
        self.installation.place_file(first, second)
        self.assertEqual(second.read_text().count(Installation.COPY_MARKER), 1)

    def test_a_copy_we_wrote_is_ours(self) -> None:
        copied = self.root / "python.md"
        self.installation.place_file(self.clone / "rules" / "python.md", copied)
        self.assertFalse(copied.is_symlink())
        self.assertTrue(self.installation.owns(copied))


class PlaceRulesTests(InstallationTestCase):
    """Rules copied into a dir by name: what is no longer wanted goes, and nothing foreign is touched."""

    def place_rules(self, names: tuple[str, ...], into: Path) -> tuple[str, ...]:
        return self.installation.place(self.installation.catalog.rule_files(names), into)

    def test_wanted_rules_land_and_dropped_ones_go(self) -> None:
        into = self.root / "dest"
        self.assertEqual(self.place_rules(("python", "git"), into), ("python", "git"))
        self.assertEqual({entry.name for entry in into.iterdir()}, {"python.md", "git.md"})
        self.place_rules(("python",), into)
        self.assertEqual({entry.name for entry in into.iterdir()}, {"python.md"})

    def test_foreign_entries_survive(self) -> None:
        into = self.root / "dest"
        into.mkdir()
        (into / "theirs.md").write_text("not ours\n")
        self.place_rules(("python",), into)
        self.place_rules((), into)
        self.assertEqual({entry.name for entry in into.iterdir()}, {"theirs.md"})

    def test_a_name_taken_by_a_foreign_file_is_skipped_with_a_warning(self) -> None:
        into = self.root / "dest"
        into.mkdir()
        (into / "git.md").write_text("hand-made\n")
        warning = self.stderr_of(lambda: self.place_rules(("git",), into))
        self.assertIn("not ours", warning)
        self.assertEqual((into / "git.md").read_text(), "hand-made\n")


class PlaceSkillsTests(InstallationTestCase):
    """Skills a target dir asked for: copied in, recorded, left alone when unchanged, and never ours to overwrite."""

    def setUp(self) -> None:
        super().setUp()
        self.registry = self.loom.registry
        self.skills_dir = self.root / "target_dir" / ".agents" / "skills"

    def place_skills(self, names: tuple[str, ...]) -> tuple[str, ...]:
        return self.installation.place(self.installation.catalog.skill_folders(names), self.skills_dir)

    def test_a_declared_skill_is_copied_in_and_recorded(self) -> None:
        self.place_skills(("translate",))
        self.assertIn("name: translate", (self.skills_dir / "translate" / "SKILL.md").read_text())
        self.assertEqual(self.registry.owned_in(self.skills_dir), ["translate"])

    def test_a_skill_cut_short_mid_copy_stays_ours(self) -> None:
        with patch("loomwork.installation.shutil.copytree", side_effect=OSError), self.assertRaises(OSError):
            self.place_skills(("translate",))
        self.assertEqual(self.registry.owned_in(self.skills_dir), ["translate"])
        self.place_skills(("translate",))
        self.assertTrue((self.skills_dir / "translate" / "SKILL.md").is_file())
        self.assertEqual(list(self.skills_dir.iterdir()), [self.skills_dir / "translate"])

    def test_a_skill_no_longer_declared_is_removed(self) -> None:
        self.place_skills(("translate",))
        self.place_skills(())
        self.assertFalse((self.skills_dir / "translate").exists())
        self.assertEqual(self.registry.owned_in(self.skills_dir), [])

    def test_a_skill_we_never_placed_is_left_alone(self) -> None:
        # the skills CLI installs into the same directory, and its entries are not ours to replace
        theirs = self.skills_dir / "translate"
        theirs.mkdir(parents=True)
        (theirs / "SKILL.md").write_text("installed by the cli\n")
        warning = self.stderr_of(lambda: self.place_skills(("translate",)))
        self.assertIn("not ours", warning)
        self.assertEqual(self.registry.owned_in(self.skills_dir), [])
        # so dropping the name later does not delete someone else's skill
        self.place_skills(())
        self.assertEqual((theirs / "SKILL.md").read_text(), "installed by the cli\n")

    def test_an_unchanged_skill_is_not_copied_again(self) -> None:
        self.place_skills(("translate",))
        written = (self.skills_dir / "translate" / "SKILL.md").stat().st_mtime_ns

        self.place_skills(("translate",))

        self.assertEqual((self.skills_dir / "translate" / "SKILL.md").stat().st_mtime_ns, written)

    def test_an_upstream_change_is_copied(self) -> None:
        self.place_skills(("translate",))
        (self.clone / "skills" / "translate" / "SKILL.md").write_text("---\nname: translate\ndescription: new\n---\n")

        self.place_skills(("translate",))

        self.assertIn("description: new", (self.skills_dir / "translate" / "SKILL.md").read_text())
