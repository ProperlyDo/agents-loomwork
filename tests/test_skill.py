from __future__ import annotations

from loomwork.skill import Skill
from tests.fixtures import SandboxTestCase


class SkillTests(SandboxTestCase):
    """What Skill reads from a SKILL.md, well-formed or not."""

    def skill_reading(self, written: str) -> Skill:
        folder = self.root / "skills" / "support"
        folder.mkdir(parents=True)
        (folder / Skill.FILE_NAME).write_text(written)
        return Skill(folder)

    def test_the_flag_marks_a_skill_manual(self) -> None:
        self.assertTrue(self.skill_reading("---\ndisable-model-invocation: true\n---\n").is_manual)

    def test_a_skill_without_the_flag_is_the_models_to_start(self) -> None:
        self.assertFalse(self.skill_reading("---\nname: support\n---\n").is_manual)

    def test_a_description_folded_over_lines_reads_as_one(self) -> None:
        skill = self.skill_reading("---\ndescription: >\n  works the board,\n  one ticket at a time\n---\n")
        self.assertEqual(skill.description, "works the board, one ticket at a time")

    def test_a_rule_drawn_in_the_body_does_not_end_up_in_the_frontmatter(self) -> None:
        skill = self.skill_reading(
            "---\ndescription: short\n---\n\n# Support\n\n---\n\ndisable-model-invocation: true\n"
        )
        self.assertEqual(skill.frontmatter, {"description": "short"})

    def test_a_file_that_opens_with_no_frontmatter_says_nothing(self) -> None:
        self.assertEqual(self.skill_reading("# Support\n\n---\nname: support\n---\n").frontmatter, {})

    def test_frontmatter_that_does_not_parse_says_nothing(self) -> None:
        self.assertEqual(self.skill_reading("---\ndescription: [unclosed\n---\n").frontmatter, {})

    def test_a_folder_without_its_skill_file_says_nothing(self) -> None:
        self.assertEqual(Skill(self.root / "skills" / "missing").frontmatter, {})
