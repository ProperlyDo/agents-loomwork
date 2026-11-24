from __future__ import annotations

import shutil

from loomwork.sources.catalog import Catalog
from loomwork.sources.manifest import Manifest
from tests.fixtures import (
    SandboxTestCase,
    make_clone,
)


class CatalogTests(SandboxTestCase):
    """What a set of sources defines, what a target dir may choose from it, and what it hands out anyway."""

    def setUp(self) -> None:
        super().setUp()
        self.clone = make_clone(self.root)

    def test_a_global_rule_is_defined_but_not_offered(self) -> None:
        # git.md reaches every target dir, declared or not, so choosing it would mean nothing
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

    def test_a_source_hands_out_only_what_it_ships(self) -> None:
        other = self.root / "other-rules"
        (other / "rules").mkdir(parents=True)
        (other / "rules" / "style.md").write_text("# Style\n")
        # python is the first source's rule, so the second marking it global hands nothing out
        (other / Manifest.FILE_NAME).write_text('[global]\nrules = ["python", "style"]\n')
        self.assertEqual(Catalog.of(self.clone, other).global_rules, ("git", "style"))
