from __future__ import annotations

from pathlib import Path

from loomwork import paths
from loomwork.agents import ClaudeCode, OpenCode
from loomwork.targets.declaration import Declaration, DeclaredSource
from tests.fixtures import (
    DECLARED_RULE,
    SOURCE,
    TEAM_SOURCE,
    InstallationTestCase,
    declare,
    make_clone,
    make_target_dir,
)


class WireTargetDirTests(InstallationTestCase):
    def setUp(self) -> None:
        super().setUp()
        # a second source with a rule of the same name, for the tests on which source wins
        self.second = make_clone(self.root, "team-rules")
        (self.second / "rules" / "python.md").write_text("# Team Python\n")
        self.loom.registry.add_source(TEAM_SOURCE, self.second, TEAM_SOURCE)

    def updated_by_wiring(self, target_dir: Path) -> list[Path]:
        return list(self.loom.wire(target_dir, ()).updated)

    def place_declared_skills(self, target_dir: Path) -> None:
        wanted = self.installation.catalog.skill_folders(Declaration.read(target_dir).skills)
        self.installation.place(wanted, paths.target_skills_dir(target_dir))

    def test_only_the_declared_rules_are_copied_in(self) -> None:
        target_dir = make_target_dir(self.root)
        self.loom.wire(target_dir, ())
        self.assertEqual({entry.name for entry in paths.target_rules_dir(target_dir).iterdir()}, {"python.md"})

    def test_unknown_rule_warns_and_is_skipped(self) -> None:
        target_dir = make_target_dir(self.root, ("python", "cobol"))
        warning = self.stderr_of(lambda: self.loom.wire(target_dir, ()))
        self.assertIn(f"unknown rule 'cobol' in {target_dir / Declaration.FILE_NAME}", warning)
        self.assertEqual({entry.name for entry in paths.target_rules_dir(target_dir).iterdir()}, {"python.md"})

    def test_an_unknown_skill_warns_and_is_skipped(self) -> None:
        target_dir = make_target_dir(self.root, skills=("missing",))
        warning = self.stderr_of(lambda: self.loom.wire(target_dir, ()))
        self.assertIn(f"unknown skill 'missing' in {target_dir / Declaration.FILE_NAME}", warning)

    def test_the_wiring_report_names_what_landed_where(self) -> None:
        target_dir = make_target_dir(self.root, ("python", "cobol"), skills=("translate",))
        self.place_declared_skills(target_dir)
        self.assertEqual(
            str(self.loom.wire(target_dir, ())).splitlines(),
            [f"wired {target_dir}", "  .agents/rules: python", "  .agents/skills: translate"],
        )

    def test_a_target_dir_that_takes_only_skills_says_so(self) -> None:
        target_dir = make_target_dir(self.root, (), skills=("translate",))
        self.place_declared_skills(target_dir)
        self.assertIn("  .agents/skills: translate", str(self.loom.wire(target_dir, ())))

    def test_the_wiring_report_names_where_each_agent_reads(self) -> None:
        target_dir = make_target_dir(self.root, ("python",))
        reported = str(self.loom.wire(target_dir, (ClaudeCode(self.claude_dir), OpenCode.from_config_dir())))
        self.assertIn("  claude reads from .claude/rules", reported)
        self.assertIn("  opencode reads from .agents/rules", reported)

    def test_dropping_the_declaration_unwires(self) -> None:
        target_dir = make_target_dir(self.root)
        self.loom.wire(target_dir, ())
        (target_dir / Declaration.FILE_NAME).unlink()
        self.loom.wire(target_dir, ())
        self.assertFalse((paths.target_rules_dir(target_dir)).exists())

    def test_another_name_for_our_source_is_still_ours(self) -> None:
        # a clone url and a bare path name one repo; a target dir is not foreign for naming it differently
        target_dir = make_target_dir(self.root, ("python",), source="git@forge.test:acme/agent-rules.git")
        self.loom.wire(target_dir, ())
        self.assertEqual({entry.name for entry in paths.target_rules_dir(target_dir).iterdir()}, {"python.md"})

    def test_a_first_pass_updates_the_rules_and_a_second_changes_nothing(self) -> None:
        target_dir = make_target_dir(self.root)
        self.assertIn(paths.target_rules_dir(target_dir), self.updated_by_wiring(target_dir))
        self.assertEqual(self.updated_by_wiring(target_dir), [])

    def test_a_rule_added_later_is_an_update(self) -> None:
        target_dir = make_target_dir(self.root)
        self.loom.wire(target_dir, ())
        declare(target_dir, ("python", "django"))
        self.assertIn(paths.target_rules_dir(target_dir), self.updated_by_wiring(target_dir))

    def test_an_upstream_edit_is_an_update(self) -> None:
        target_dir = make_target_dir(self.root)
        self.loom.wire(target_dir, ())
        (self.clone / "rules" / "python.md").write_text(DECLARED_RULE + "- a rule added upstream\n")
        self.assertIn(paths.target_rules_dir(target_dir), self.updated_by_wiring(target_dir))

    def test_a_dropped_rule_is_an_update(self) -> None:
        target_dir = make_target_dir(self.root, ("python", "django"))
        self.loom.wire(target_dir, ())
        declare(target_dir, ("python",))
        self.assertIn(paths.target_rules_dir(target_dir), self.updated_by_wiring(target_dir))

    def test_rules_are_copied_not_linked(self) -> None:
        # a link here resolves outside the target dir, which Claude gates behind an approval nothing raises
        target_dir = make_target_dir(self.root)
        self.loom.wire(target_dir, ())
        copied = paths.target_rules_dir(target_dir) / "python.md"
        self.assertFalse(copied.is_symlink())
        self.assertIn("# Python", copied.read_text())

    def test_the_later_declared_source_wins_a_shared_filename(self) -> None:
        target_dir = make_target_dir(self.root, ())
        Declaration((DeclaredSource(SOURCE), DeclaredSource(TEAM_SOURCE, ("python",)))).write(target_dir)
        self.loom.wire(target_dir, ())
        self.assertIn("# Team Python", (paths.target_rules_dir(target_dir) / "python.md").read_text())

    def test_a_source_the_target_dir_does_not_declare_supplies_nothing(self) -> None:
        # the team source sits in loom's registry for another target dir, and must not shadow this one's python
        target_dir = make_target_dir(self.root, ("python",))
        self.loom.wire(target_dir, ())
        self.assertNotIn("# Team Python", (paths.target_rules_dir(target_dir) / "python.md").read_text())
