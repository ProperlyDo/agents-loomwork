from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

from loomwork import paths
from loomwork.agents import Agent, ClaudeCode, OpenCode
from loomwork.declaration import Declaration, Manifest
from loomwork.installation import Installation
from loomwork.loom import WiringReport
from loomwork.sources import Catalog
from tests.fixtures import DECLARED_RULE, GLOBAL_RULE, SandboxTestCase, declare, make_clone, make_project


class InstallationTestCase(SandboxTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.clone = make_clone(self.root)
        self.sources = (self.clone,)

    @property
    def installation(self) -> Installation:
        """Built on every use, as loom does, so a source changed after setUp is read as it now is."""
        return Installation(catalog=Catalog.of(*self.sources), registry=self.loom.registry)

    def wire_project(
        self, project: Path, agents: tuple[Agent, ...] = (), installation: Installation | None = None
    ) -> WiringReport:
        """What a sync does for one project, with these agents chosen for it."""
        self.loom.registry.add_project(project, [agent.NAME for agent in agents])
        return self.loom.wire(installation or self.installation, project)


class OwnershipTests(InstallationTestCase):
    def test_a_link_into_its_projects_agents_dir_is_ours_even_dangling(self) -> None:
        # .agents/ may be gone, and a link we laid still has to be ours to remove
        rules_dir = self.root / "project" / ".claude" / "rules"
        rules_dir.mkdir(parents=True)
        (rules_dir / "loom").symlink_to("../../.agents/rules")
        self.assertTrue(self.installation.owned(rules_dir / "loom"))

    def test_a_link_into_another_projects_agents_dir_is_foreign(self) -> None:
        (self.root / "here").mkdir()
        link = self.root / "here" / "python.md"
        link.symlink_to(self.root / "elsewhere" / ".agents" / "rules" / "python.md")
        self.assertFalse(self.installation.owned(link))

    def test_a_link_into_a_source_is_foreign(self) -> None:
        link = self.root / "git.md"
        link.symlink_to(self.clone / "rules" / "git.md")
        self.assertFalse(self.installation.owned(link))

    def test_a_relative_link_from_the_skills_cli_is_foreign(self) -> None:
        # the skills CLI links its installs relatively; clearing those would delete a neighbour's work
        (self.root / "skills" / "find-skills").mkdir(parents=True)
        link = self.root / "find-skills"
        link.symlink_to("skills/find-skills")
        self.assertFalse(self.installation.owned(link))

    def test_a_dangling_link_aiming_elsewhere_is_foreign(self) -> None:
        link = self.root / "python.md"
        link.symlink_to(self.root / "moved-away" / "rules" / "python.md")
        self.assertFalse(self.installation.owned(link))

    def test_real_file_is_never_ours(self) -> None:
        rule = self.root / "hand-written.md"
        rule.write_text("mine\n")
        self.assertFalse(self.installation.owned(rule))

    def test_a_copy_of_a_copy_carries_one_marker(self) -> None:
        first = self.root / "python.md"
        second = self.root / "python-again.md"
        self.installation.place_file(self.clone / "rules" / "python.md", first)
        self.installation.place_file(first, second)
        self.assertEqual(second.read_text().count(Installation.COPY_MARKER), 1)

    def test_a_copy_we_wrote_is_ours(self) -> None:
        copy = self.root / "python.md"
        self.installation.place_file(self.clone / "rules" / "python.md", copy)
        self.assertFalse(copy.is_symlink())
        self.assertTrue(self.installation.owned(copy))


class SeveralSourcesTests(InstallationTestCase):
    """A profile can have more than one source added; the later one wins a filename."""

    def setUp(self) -> None:
        super().setUp()
        self.second = make_clone(self.root, "team-rules")
        (self.second / "rules" / "python.md").write_text("# Team Python\n")
        self.sources = (self.clone, self.second)

    def test_the_later_source_wins_a_shared_filename(self) -> None:
        project = make_project(self.root, ("python",))
        self.wire_project(project)
        self.assertIn("# Team Python", (project / ".agents" / "rules" / "python.md").read_text())


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


class WireProjectTests(InstallationTestCase):
    def copied_rules_of(self, project: Path) -> Path:
        return project / ".agents" / "rules"

    def updated_by_wiring(self, project: Path) -> list[Path]:
        installation = self.installation
        self.wire_project(project, installation=installation)
        return installation.updated

    def place_declared_skills(self, project: Path) -> None:
        wanted = self.installation.catalog.skill_folders(Declaration.read(project).skills)
        self.installation.place(wanted, paths.project_skills_dir(project))

    def test_only_the_declared_rules_are_copied_in(self) -> None:
        project = make_project(self.root)
        self.wire_project(project)
        self.assertEqual({entry.name for entry in self.copied_rules_of(project).iterdir()}, {"python.md"})

    def test_unknown_rule_warns_and_is_skipped(self) -> None:
        project = make_project(self.root, ("python", "cobol"))
        warning = self.stderr_of(lambda: self.wire_project(project))
        self.assertIn(f"unknown rule 'cobol' in {project / Declaration.FILE_NAME}", warning)
        self.assertEqual({entry.name for entry in self.copied_rules_of(project).iterdir()}, {"python.md"})

    def test_an_unknown_skill_warns_and_is_skipped(self) -> None:
        project = make_project(self.root, skills=("missing",))
        warning = self.stderr_of(lambda: self.wire_project(project))
        self.assertIn(f"unknown skill 'missing' in {project / Declaration.FILE_NAME}", warning)

    def test_the_wiring_report_names_what_landed_where(self) -> None:
        project = make_project(self.root, ("python", "cobol"), skills=("translate",))
        self.place_declared_skills(project)
        self.assertEqual(
            str(self.wire_project(project)).splitlines(),
            [f"wired {project}", "  .agents/rules: python", "  .agents/skills: translate"],
        )

    def test_a_project_that_takes_only_skills_says_so(self) -> None:
        project = make_project(self.root, (), skills=("translate",))
        self.place_declared_skills(project)
        self.assertIn("  .agents/skills: translate", str(self.wire_project(project)))

    def test_the_wiring_report_names_where_each_agent_reads(self) -> None:
        project = make_project(self.root, ("python",))
        reported = str(self.wire_project(project, (ClaudeCode(self.claude_dir), OpenCode())))
        self.assertIn("  claude reads from .claude/rules", reported)
        self.assertIn("  opencode reads from .agents/rules", reported)

    def test_dropping_the_declaration_unwires(self) -> None:
        project = make_project(self.root)
        self.wire_project(project)
        (project / Declaration.FILE_NAME).unlink()
        self.wire_project(project)
        self.assertFalse((project / ".agents" / "rules").exists())

    def test_another_spelling_of_our_source_is_still_ours(self) -> None:
        # a clone url and a bare path name one repo; a project is not foreign for spelling it differently
        project = make_project(self.root, ("python",), source="git@forge.test:acme/agent-rules.git")
        self.wire_project(project)
        self.assertEqual({entry.name for entry in self.copied_rules_of(project).iterdir()}, {"python.md"})

    def test_a_first_pass_updates_the_rules_and_a_second_changes_nothing(self) -> None:
        project = make_project(self.root)
        self.assertIn(self.copied_rules_of(project), self.updated_by_wiring(project))
        self.assertEqual(self.updated_by_wiring(project), [])

    def test_a_rule_added_later_is_an_update(self) -> None:
        project = make_project(self.root)
        self.wire_project(project)
        declare(project, ("python", "django"))
        self.assertIn(self.copied_rules_of(project), self.updated_by_wiring(project))

    def test_an_upstream_edit_is_an_update(self) -> None:
        project = make_project(self.root)
        self.wire_project(project)
        (self.clone / "rules" / "python.md").write_text(DECLARED_RULE + "- a rule added upstream\n")
        self.assertIn(self.copied_rules_of(project), self.updated_by_wiring(project))

    def test_a_dropped_rule_is_an_update(self) -> None:
        project = make_project(self.root, ("python", "django"))
        self.wire_project(project)
        declare(project, ("python",))
        self.assertIn(self.copied_rules_of(project), self.updated_by_wiring(project))

    def test_rules_are_copied_not_linked(self) -> None:
        # a link here resolves outside the project, which Claude gates behind an approval nothing raises
        project = make_project(self.root)
        self.wire_project(project)
        copy = self.copied_rules_of(project) / "python.md"
        self.assertFalse(copy.is_symlink())
        self.assertIn("# Python", copy.read_text())


class ClaudeCodeTests(InstallationTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.claude_dir.mkdir(parents=True)
        self.agent = ClaudeCode(self.claude_dir)

    def test_a_source_that_hands_out_nothing_leaves_no_dir(self) -> None:
        (self.clone / Manifest.FILE_NAME).unlink()
        self.agent.bridge(self.installation)
        self.assertFalse((self.claude_dir / "rules").exists())

    def test_only_rules_handed_to_everyone_bridge_globally(self) -> None:
        self.agent.bridge(self.installation)
        bridged = self.claude_dir / "rules"
        self.assertEqual({entry.name for entry in bridged.iterdir()}, {"git.md"})
        self.assertIn("# Agent Instructions", (self.claude_dir / "CLAUDE.md").read_text())

    def test_a_foreign_skill_survives_the_bridge(self) -> None:
        theirs = self.claude_dir / "skills" / "theirs"
        theirs.mkdir(parents=True)
        self.agent.bridge(self.installation)
        self.assertTrue(theirs.is_dir())

    def test_a_global_skill_is_copied_into_the_agents_own_skills_dir(self) -> None:
        (self.clone / "skills" / "everywhere").mkdir(parents=True)
        (self.clone / "skills" / "everywhere" / "SKILL.md").write_text("---\nname: everywhere\n---\n")
        (self.clone / Manifest.FILE_NAME).write_text('[global]\nskills = ["everywhere"]\n')

        self.agent.bridge(self.installation)

        placed = self.claude_dir / "skills" / "everywhere"
        self.assertTrue((placed / "SKILL.md").is_file())
        self.assertFalse(placed.is_symlink())

    def test_unbridging_takes_back_the_global_skills_only(self) -> None:
        (self.clone / Manifest.FILE_NAME).write_text('[global]\nskills = ["translate"]\n')
        theirs = self.claude_dir / "skills" / "theirs"
        theirs.mkdir(parents=True)
        self.agent.bridge(self.installation)
        self.agent.unbridge(self.installation)
        self.assertFalse((self.claude_dir / "skills" / "translate").exists())
        self.assertTrue(theirs.is_dir())

    def test_project_rules_sit_beside_the_projects_own(self) -> None:
        project = make_project(self.root)
        own = project / ".claude" / "rules" / "team.md"
        own.parent.mkdir(parents=True)
        own.write_text("# Team\n")
        self.wire_project(project, (self.agent,))
        rules_link = project / ".claude" / "rules" / "loom"
        # relative, because Claude never loads a project rule whose link resolves outside the project
        self.assertFalse(rules_link.readlink().is_absolute())
        self.assertEqual(rules_link.resolve(), paths.project_rules_dir(project).resolve())
        self.assertEqual(own.read_text(), "# Team\n")

    def test_each_skill_is_linked_beside_the_projects_own(self) -> None:
        project = make_project(self.root, skills=("translate",))
        own = project / ".claude" / "skills" / "deploy"
        own.mkdir(parents=True)
        wanted = self.installation.catalog.skill_folders(("translate",))
        self.installation.place(wanted, paths.project_skills_dir(project))
        self.wire_project(project, (self.agent,))
        self.assertTrue((project / ".claude" / "skills" / "translate" / "SKILL.md").is_file())
        self.assertTrue(own.is_dir())

    def test_a_foreign_claude_md_is_left_alone_and_not_reported(self) -> None:
        (self.claude_dir / "CLAUDE.md").write_text("# Mine\n")
        self.assertNotIn(self.claude_dir / "CLAUDE.md", self.agent.bridge(self.installation))
        self.assertEqual((self.claude_dir / "CLAUDE.md").read_text(), "# Mine\n")


class ProfileHookTests(InstallationTestCase):
    """The hook a profile gets: guarded by the declaration, merged beside whatever is already there."""

    def setUp(self) -> None:
        super().setUp()
        self.agent = ClaudeCode(self.claude_dir)
        self.settings_file = self.agent.config_dir / "settings.json"

    def hooks_in_settings(self) -> list[str]:
        entries = json.loads(self.settings_file.read_text())["hooks"]["SessionStart"]
        return [hook["command"] for entry in entries for hook in entry["hooks"]]

    def write_foreign_hook(self) -> None:
        self.settings_file.parent.mkdir(parents=True, exist_ok=True)
        foreign = {"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "echo theirs"}]}]}}
        self.settings_file.write_text(json.dumps(foreign))

    def test_the_hook_runs_nothing_where_a_project_never_opted_in(self) -> None:
        self.agent.bridge(self.installation)
        command = self.hooks_in_settings()[0]
        self.assertIn(Declaration.FILE_NAME, command)
        self.assertIn("exit 0", command)
        self.assertTrue(command.endswith('sync --for claude "$CLAUDE_PROJECT_DIR"'))

    def test_the_hook_names_the_profile_it_was_registered_in(self) -> None:
        # a session of another profile runs its own hook, so each one must sync its own registry
        self.agent.bridge(self.installation)
        self.assertIn(f"--config-dir {self.claude_dir} sync", self.hooks_in_settings()[0])

    def test_the_hook_calls_loom_where_it_was_started_from(self) -> None:
        # run from a checkout with `uv run`, loom is on no PATH a hook's shell knows
        started = self.root / "checkout" / ".venv" / "bin" / "loom"
        started.parent.mkdir(parents=True)
        started.write_text("#!/bin/sh\n")
        started.chmod(0o755)
        with patch("sys.argv", [str(started)]):
            self.agent.bridge(self.installation)
        self.assertTrue(self.hooks_in_settings()[0].split("; ", 1)[1].startswith(f"{started} --config-dir"))

    def test_registering_twice_keeps_one_of_ours_and_every_foreign_hook(self) -> None:
        self.write_foreign_hook()
        self.agent.bridge(self.installation)
        self.agent.bridge(self.installation)
        commands = self.hooks_in_settings()
        self.assertEqual(commands.count("echo theirs"), 1)
        self.assertEqual(len([command for command in commands if " sync " in command]), 1)

    def test_unbridging_leaves_the_foreign_hooks(self) -> None:
        self.write_foreign_hook()
        self.agent.bridge(self.installation)
        self.agent.unbridge(self.installation)
        self.assertEqual(self.hooks_in_settings(), ["echo theirs"])

    def test_a_hook_is_ours_whatever_path_it_was_written_with(self) -> None:
        for command in ("loom sync /x", "/opt/homebrew/bin/loom sync /x"):
            self.assertTrue(self.agent.our_hook(self.installation, {"command": command}), command)

    def test_a_foreign_sync_command_is_not_ours(self) -> None:
        self.assertFalse(self.agent.our_hook(self.installation, {"command": "rsync sync /x"}))
        self.assertFalse(self.agent.our_hook(self.installation, {"command": "echo loom sync"}))


class OpenCodeTests(InstallationTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.agent = OpenCode()

    def test_its_agents_file_comes_and_goes_with_the_bridge(self) -> None:
        self.agent.bridge(self.installation)
        self.assertIn("# Agent Instructions", (self.agent.config_dir / "AGENTS.md").read_text())
        self.agent.unbridge(self.installation)
        self.assertFalse((self.agent.config_dir / "AGENTS.md").exists())

    def test_the_global_rules_land_in_its_rules_dir(self) -> None:
        self.agent.bridge(self.installation)
        self.assertEqual({rule.name for rule in (self.agent.config_dir / "rules").iterdir()}, {"git.md"})
        self.assertNotIn(GLOBAL_RULE.strip(), (self.agent.config_dir / "AGENTS.md").read_text())

    def test_an_agent_that_never_ran_here_is_written_for_anyway(self) -> None:
        # loom distributes where it is told; a missing config dir is made, not a reason to refuse
        self.assertFalse(self.agent.config_dir.exists())
        self.agent.bridge(self.installation)
        self.assertTrue((self.agent.config_dir / "AGENTS.md").is_file())

    def test_an_empty_xdg_config_home_falls_back_to_the_home_config(self) -> None:
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": ""}):
            self.assertEqual(OpenCode().config_dir, Path("~/.config/opencode").expanduser())


class UniversalLayerTests(InstallationTestCase):
    def test_a_source_without_one_still_hands_out_its_rules(self) -> None:
        (self.clone / "AGENTS.md").unlink()
        self.claude_dir.mkdir(parents=True)
        project = make_project(self.root, rules=("python",))
        agent = ClaudeCode(self.claude_dir)
        agent.bridge(self.installation)
        self.wire_project(project, (agent,))
        self.assertTrue((project / ".agents" / "rules" / "python.md").is_file())
        self.assertFalse((self.claude_dir / "CLAUDE.md").exists())


class PlaceSkillsTests(InstallationTestCase):
    """Skills a project asked for: copied in, recorded, left alone when unchanged, and never ours to overwrite."""

    def setUp(self) -> None:
        super().setUp()
        self.registry = self.loom.registry
        self.skills_dir = self.root / "project" / ".agents" / "skills"

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
