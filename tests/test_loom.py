from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

from loomwork import paths
from loomwork.agents import Agent, ClaudeCode, OpenCode
from loomwork.errors import LoomError
from loomwork.loom import Loom
from loomwork.sources.manifest import Manifest
from loomwork.targets.declaration import Declaration, DeclaredSource
from loomwork.targets.gitignore import Gitignore
from tests.fixtures import (
    SOURCE,
    TEAM_SOURCE,
    SandboxTestCase,
    WiredTargetDirTestCase,
    declare,
    make_clone,
    make_target_dir,
)

if TYPE_CHECKING:
    from pathlib import Path


class SetupsApartTests(SandboxTestCase):
    """Two setups on one machine: the standard dirs with one source, and dirs of their own with another."""

    def setUp(self) -> None:
        super().setUp()
        # the sources are filed under repo addresses, so an update takes the clone's way to the remote
        self.enterContext(patch("loomwork.git.match_remote", return_value=True))
        self.loom.registry.add_source(SOURCE, make_clone(self.root), SOURCE)
        self.loom.registry.add_source(TEAM_SOURCE, self.make_work_clone(), TEAM_SOURCE)
        self.target_dir = make_target_dir(self.root)
        self.work_target_dir = self.root / "work-target"
        self.work_target_dir.mkdir()
        declare(self.work_target_dir, ("python",), source=TEAM_SOURCE)
        self.standard = self.loom.agents_named((ClaudeCode.NAME, OpenCode.NAME))
        self.claude_work_dir = self.home / ".claude-work"
        self.opencode_work_dir = self.home / ".config" / "opencode-work"
        self.work = Loom(
            self.loom.registry, {ClaudeCode.NAME: self.claude_work_dir, OpenCode.NAME: self.opencode_work_dir}
        )
        self.work_agents = self.work.agents_named((ClaudeCode.NAME, OpenCode.NAME))

    def make_work_clone(self) -> Path:
        """A source that differs from the standard setup's in its layer, its global rule and a global manual skill."""
        clone = make_clone(self.root, "work-rules")
        (clone / "AGENTS.md").write_text("# Work Instructions\n")
        (clone / "rules" / "gitlab.md").write_text("# GitLab\n")
        (clone / "skills" / "support").mkdir()
        (clone / "skills" / "support" / "SKILL.md").write_text("---\ndisable-model-invocation: true\n---\n")
        (clone / Manifest.FILE_NAME).write_text('[global]\nrules = ["gitlab"]\nskills = ["support"]\n')
        return clone

    def wire_both(self) -> None:
        self.loom._add_target_dir(self.target_dir, self.standard)
        self.work._add_target_dir(self.work_target_dir, self.work_agents)

    def test_each_setup_writes_into_its_own_dirs(self) -> None:
        self.wire_both()
        standard_opencode = self.standard[1].config_dir
        self.assertIn("# Agent Instructions", (standard_opencode / "AGENTS.md").read_text())
        self.assertEqual([rule.name for rule in (standard_opencode / "rules").iterdir()], ["git.md"])
        self.assertFalse((standard_opencode / "commands").exists())
        self.assertIn("# Work Instructions", (self.opencode_work_dir / "AGENTS.md").read_text())
        self.assertEqual([rule.name for rule in (self.opencode_work_dir / "rules").iterdir()], ["gitlab.md"])
        self.assertEqual([command.name for command in (self.opencode_work_dir / "commands").iterdir()], ["support.md"])
        self.assertIn("# Work Instructions", (self.claude_work_dir / "CLAUDE.md").read_text())
        self.assertIn("# Agent Instructions", (self.claude_dir / "CLAUDE.md").read_text())

    def test_a_sync_needs_no_dirs_to_find_where_a_target_dir_is_wired_from(self) -> None:
        self.wire_both()
        (self.opencode_work_dir / "rules" / "gitlab.md").unlink()
        self.loom.sync(self.work_target_dir)
        self.assertTrue((self.opencode_work_dir / "rules" / "gitlab.md").is_file())
        self.assertEqual([rule.name for rule in self.standard[1].rules_dir.iterdir()], ["git.md"])

    def test_a_session_of_the_other_setup_is_told_which_dir_to_launch_with(self) -> None:
        self.wire_both()
        said = self.stdout_of(lambda: self.loom.sync(self.work_target_dir, self.standard[0]))
        self.assertIn(f"{ClaudeCode.CONFIG_DIR_ENV}=~/.claude-work claude", said)
        self.assertEqual(
            self.loom.registry.config_dirs_of(self.work_target_dir), [self.claude_work_dir, self.opencode_work_dir]
        )
        self.assertFalse((self.claude_dir / "rules" / "gitlab.md").exists())

    def test_a_session_of_another_dir_in_a_standard_setups_target_dir_is_told_to_drop_the_variable(self) -> None:
        self.wire_both()
        said = self.stdout_of(lambda: self.work.sync(self.target_dir, self.work_agents[0]))
        self.assertIn(f"launch claude without {ClaudeCode.CONFIG_DIR_ENV}", said)

    def test_a_target_dir_wired_from_two_dirs_of_one_agent_is_left_alone_for_it(self) -> None:
        self.wire_both()
        self.loom.registry.add_target_dir(self.claude_dir, self.work_target_dir, [TEAM_SOURCE])
        said = self.stderr_of(lambda: self.loom.sync(self.work_target_dir))
        self.assertEqual(len(said.splitlines()), 1)
        self.assertIn("is wired for claude from ~/.claude, ~/.claude-work", said)

    def test_wiring_from_another_dir_moves_the_target_dir(self) -> None:
        self.work._add_target_dir(self.work_target_dir, self.work_agents)
        said = self.stdout_of(lambda: self.loom._add_target_dir(self.work_target_dir, self.standard[:1]))
        self.assertIn("moved claude from ~/.claude-work to ~/.claude", said)
        self.assertEqual(self.loom.registry.config_dirs_of(self.work_target_dir), [self.claude_dir])
        self.assertTrue((self.work_target_dir / ".claude" / "rules" / "loom").is_symlink())

    def test_a_config_dir_a_target_dir_leaves_loses_the_global_files_only_it_brought(self) -> None:
        self.work._add_target_dir(self.work_target_dir, self.work_agents)
        self.loom._add_target_dir(self.work_target_dir, self.standard[:1])
        self.assertFalse((self.claude_work_dir / "rules" / "gitlab.md").exists())
        self.assertFalse((self.claude_work_dir / "CLAUDE.md").exists())

    def test_init_says_how_to_launch_an_agent_for_a_dir_of_its_own(self) -> None:
        said = self.stdout_of(lambda: self.work.init(self.work_target_dir, self.work_agents))
        self.assertIn(f"{OpenCode.CONFIG_DIR_ENV}=~/.config/opencode-work opencode --standalone", said)
        self.assertNotIn(
            OpenCode.CONFIG_DIR_ENV, self.stdout_of(lambda: self.loom.init(self.target_dir, self.standard))
        )

    def test_uninstalling_empties_every_dir(self) -> None:
        self.wire_both()
        self.loom.uninstall()
        self.assertFalse(self.opencode_work_dir.exists())
        self.assertFalse((self.claude_dir / "CLAUDE.md").exists())
        self.assertFalse(self.loom.registry.path.exists())


class RegistryFollowsWiringTests(WiredTargetDirTestCase):
    """Whatever wires a target dir records it — a hook-driven sync counts as much as a hand-typed init."""

    def test_a_hook_driven_sync_records_the_target_dir_with_the_agent_that_asked(self) -> None:
        # without the agent, every later sync would wire none — a skill added later would never reach Claude
        self.loom.sync(self.target_dir, self.claude)
        self.assertEqual(self.loom.registry.config_dirs_of(self.target_dir), [self.claude_dir])

    def test_an_agent_left_out_of_a_new_choice_is_unwired(self) -> None:
        self.loom._add_target_dir(self.target_dir, (self.claude, self.opencode))
        self.assertTrue((self.target_dir / ".claude" / "rules" / "loom").is_symlink())
        self.loom._add_target_dir(self.target_dir, (self.opencode,))
        self.assertFalse((self.target_dir / ".claude").exists())
        self.assertEqual([agent.NAME for agent in self.loom.wired_agents(self.target_dir)], [OpenCode.NAME])

    def test_removing_a_target_dir_takes_its_skills_but_not_foreign_ones(self) -> None:
        declare(self.target_dir, ("python",), skills=("translate",))
        theirs = paths.target_skills_dir(self.target_dir) / "from-the-cli"
        theirs.mkdir(parents=True)
        self.loom._add_target_dir(self.target_dir, (self.claude,))
        self.assertTrue((paths.target_skills_dir(self.target_dir) / "translate" / "SKILL.md").is_file())
        self.loom.remove(self.target_dir)
        self.assertFalse((paths.target_skills_dir(self.target_dir) / "translate").exists())
        self.assertTrue(theirs.is_dir())
        self.assertEqual(self.loom.registry.target_dirs, [])

    def test_a_session_of_another_agent_adds_to_what_was_chosen(self) -> None:
        self.loom._add_target_dir(self.target_dir, (self.opencode,))
        self.loom.sync(self.target_dir, self.claude)
        self.assertEqual(
            sorted(agent.NAME for agent in self.loom.wired_agents(self.target_dir)), [ClaudeCode.NAME, OpenCode.NAME]
        )

    def test_a_target_dir_that_dropped_its_declaration_is_forgotten(self) -> None:
        self.loom.sync(self.target_dir, self.claude)
        (self.target_dir / Declaration.FILE_NAME).unlink()
        self.loom.sync(self.target_dir)
        self.assertEqual(self.loom.registry.target_dirs, [])

    def test_removing_an_unrecorded_target_dir_still_takes_our_links(self) -> None:
        self.loom._add_target_dir(self.target_dir, (self.claude,))
        self.loom.registry.forget()
        self.loom.remove(self.target_dir)
        self.assertFalse((self.target_dir / ".claude" / "rules" / "loom").is_symlink())


class ChosenAgentsTests(SandboxTestCase):
    """Which agents a target dir is wired for: what it was set up for, each from its dir."""

    def setUp(self) -> None:
        super().setUp()
        self.target_dir = self.root / "target_dir"
        opencode_dir = OpenCode.standard_config_dir()
        self.loom.registry.add_config_dir(opencode_dir, OpenCode.NAME)

    def test_a_recorded_choice_is_what_gets_wired(self) -> None:
        self.loom.registry.add_target_dir(OpenCode.standard_config_dir(), self.target_dir, [])
        self.assertEqual([agent.NAME for agent in self.loom.wired_agents(self.target_dir)], [OpenCode.NAME])

    def test_a_target_dir_nobody_chose_for_gets_nothing(self) -> None:
        self.assertEqual(self.loom.wired_agents(self.target_dir), ())

    def test_the_recorded_choice_is_what_init_offers_ticked(self) -> None:
        self.loom.registry.add_target_dir(OpenCode.standard_config_dir(), self.target_dir, [])
        self.assertEqual(self.loom.usual_agents(self.target_dir), (OpenCode.NAME,))

    def test_a_new_target_dir_is_offered_what_is_installed(self) -> None:
        with patch.object(Agent, "is_present", autospec=True, side_effect=lambda agent: agent.NAME == ClaudeCode.NAME):
            self.assertIn(ClaudeCode.NAME, self.loom.usual_agents(self.target_dir))
            self.assertNotIn(OpenCode.NAME, self.loom.usual_agents(self.target_dir))


class UninstallTests(WiredTargetDirTestCase):
    def test_uninstall_clears_an_agent_that_is_not_installed(self) -> None:
        self.loom._add_target_dir(self.target_dir, (self.opencode,))
        agents_md = self.opencode.config_dir / "AGENTS.md"
        self.assertTrue(agents_md.is_file())
        with patch.object(Agent, "is_present", return_value=False):
            self.loom.uninstall()
        self.assertFalse(agents_md.exists())


class InitTests(SandboxTestCase):
    """What init sets up from its answers, and what it leaves alone when it cannot go on."""

    def setUp(self) -> None:
        super().setUp()
        self.clone = make_clone(self.root, "acme-rules")
        self.loom.registry.add_source(SOURCE, self.clone, SOURCE)

    def test_init_writes_the_answered_declaration_and_gitignore_then_wires(self) -> None:
        target_dir = self.root / "fresh"
        target_dir.mkdir()
        declaration = Declaration((DeclaredSource(SOURCE, ("python",)),))
        self.loom.init(
            target_dir, self.loom.agents_named((ClaudeCode.NAME,)), declaration=declaration, ignore_generated=True
        )
        self.assertEqual(Declaration.read(target_dir), declaration)
        self.assertIn(".agents/", (target_dir / Gitignore.FILE_NAME).read_text())
        self.assertTrue((paths.target_rules_dir(target_dir) / "python.md").is_file())
        self.assertEqual(self.loom.registry.config_dirs_of(target_dir), [self.claude_dir])

    def test_init_without_a_declaration_sets_up_the_dirs_and_wires_nothing(self) -> None:
        target_dir = self.root / "undeclared"
        target_dir.mkdir()
        # a local checkout that was never pushed, pinned with init --source
        self.enterContext(patch("loomwork.git.origin", return_value=None))
        said = self.stderr_of(
            lambda: self.loom.init(target_dir, self.loom.agents_named((ClaudeCode.NAME,)), source=str(self.clone))
        )
        self.assertIn(f"carries no {Declaration.FILE_NAME}", said)
        self.assertTrue((self.claude_dir / "rules" / "git.md").is_file())
        self.assertEqual(self.loom.registry.config_dirs_of(target_dir), [])

    def test_without_a_source_init_says_what_to_run(self) -> None:
        bare = self.root / "bare"
        bare.mkdir()
        with self.assertRaises(LoomError):
            self.loom.init(bare, self.loom.agents_named((ClaudeCode.NAME,)))

    def test_init_places_the_global_skills_in_the_same_run(self) -> None:
        (self.clone / Manifest.FILE_NAME).write_text('[global]\nskills = ["translate"]\n')
        target_dir = make_target_dir(self.root)
        self.loom.init(target_dir, self.loom.agents_named((ClaudeCode.NAME,)))
        self.assertTrue((self.claude_dir / "skills" / "translate" / "SKILL.md").is_file())

    def test_init_takes_the_source_from_what_the_target_dir_declares(self) -> None:
        # the first teammate on a fresh machine has a committed declaration and should be asked nothing
        target_dir = make_target_dir(self.root, source="forge.test/other/rules")
        fetched = make_clone(self.root, "other-rules")
        with patch("loomwork.sources.source.Source.fetch", return_value=fetched):
            self.loom.init(target_dir, ())
        self.assertEqual(self.loom.registry.checkout_of("forge.test/other/rules"), fetched)

    def test_a_source_that_cannot_be_fetched_leaves_the_target_dir_untouched(self) -> None:
        target_dir = self.root / "fresh"
        target_dir.mkdir()
        declaration = Declaration((DeclaredSource(SOURCE, ("python",)),))
        with (
            patch("loomwork.sources.source.Source.fetch", side_effect=LoomError("clone_failed", "unreachable")),
            self.assertRaises(LoomError),
        ):
            self.loom.init(target_dir, self.loom.agents_named((ClaudeCode.NAME,)), "forge.test/acme/gone", declaration)
        self.assertFalse((target_dir / Declaration.FILE_NAME).exists())

    def test_init_asks_for_no_restart(self) -> None:
        # no session is open yet to restart
        target_dir = make_target_dir(self.root)
        said = self.stdout_of(lambda: self.loom.init(target_dir, self.loom.agents_named((ClaudeCode.NAME,))))
        self.assertNotIn("restart", said)

    def test_the_default_source_is_the_one_most_target_dirs_declare(self) -> None:
        self.loom.registry.add_config_dir(self.claude_dir, ClaudeCode.NAME)
        for name in ("one", "two"):
            target_dir = self.root / name
            target_dir.mkdir()
            Declaration((DeclaredSource(SOURCE, ("python",)),)).write(target_dir)
            self.loom.registry.add_target_dir(self.claude_dir, target_dir, [SOURCE])
        odd = self.root / "odd"
        odd.mkdir()
        Declaration((DeclaredSource("forge.test/other/rules", ()),)).write(odd)
        self.loom.registry.add_target_dir(self.claude_dir, odd, [])

        self.assertEqual(self.loom.most_declared_source(), SOURCE)


class ReportingTests(SandboxTestCase):
    """What status and sync tell the user."""

    def setUp(self) -> None:
        super().setUp()
        self.clone = make_clone(self.root)
        self.loom.registry.add_source(SOURCE, self.clone, SOURCE)
        self.loom.registry.add_config_dir(self.claude_dir, ClaudeCode.NAME)
        self.loom.registry.pin_source(self.claude_dir, SOURCE)

    def test_status_names_each_dir_and_what_every_target_dir_gets_anyway(self) -> None:
        # no target dir's declaration mentions them, so status is the only place they are visible
        said = self.stdout_of(self.loom.status)
        self.assertIn("claude ~/.claude", said)
        self.assertIn("every target dir gets rules: git", said)

    def test_syncing_an_undeclared_target_dir_says_so(self) -> None:
        bare = self.root / "bare"
        bare.mkdir()
        self.assertIn("nothing to sync", self.stderr_of(lambda: self.loom.sync(bare)))
