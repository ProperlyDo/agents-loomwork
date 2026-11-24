from __future__ import annotations

from unittest.mock import patch

from loomwork.agents import Agent, ClaudeCode
from loomwork.cli.interview import InitInterview
from loomwork.errors import LoomError
from loomwork.targets.declaration import Declaration
from tests.fixtures import SOURCE, SandboxTestCase, declare, leaving_a_mark, make_clone, times_marked


class InitInterviewTests(SandboxTestCase):
    """What init asks, what it stops asking once the answer is recorded, and what it refuses."""

    def setUp(self) -> None:
        super().setUp()
        self.loom.registry.add_source(SOURCE, make_clone(self.root), SOURCE)
        self.target_dir = self.root / "target_dir"
        self.claude = self.loom.agents_named((ClaudeCode.NAME,))
        self.interview = InitInterview(self.loom, self.target_dir, agent_names=None, source=None)

    def test_a_dir_with_a_pinned_source_is_not_asked_for_one(self) -> None:
        self.loom.registry.add_config_dir(self.claude_dir, ClaudeCode.NAME)
        self.loom.registry.pin_source(self.claude_dir, SOURCE)
        with patch("loomwork.cli.prompts.can_ask", return_value=True):
            self.assertIsNone(self.interview._wanted_source(self.claude, None))

    def test_a_dir_whose_target_dirs_declare_a_source_is_not_asked_for_one(self) -> None:
        self.loom.registry.add_config_dir(self.claude_dir, ClaudeCode.NAME)
        self.loom.registry.add_target_dir(self.claude_dir, self.root / "other", [SOURCE])
        with patch("loomwork.cli.prompts.can_ask", return_value=True):
            self.assertIsNone(self.interview._wanted_source(self.claude, None))

    def test_a_move_off_another_dir_is_refused_when_nobody_can_say(self) -> None:
        work_dir = self.home / ".claude-work"
        self.loom.registry.add_config_dir(work_dir, ClaudeCode.NAME)
        self.loom.registry.add_target_dir(work_dir, self.target_dir, [SOURCE])
        with patch("loomwork.cli.prompts.can_ask", return_value=False), self.assertRaises(LoomError) as refused:
            self.interview._confirm_moves(self.claude)
        self.assertEqual(refused.exception.code, "move_needs_a_terminal")
        self.assertIn("would move claude from ~/.claude-work to ~/.claude", str(refused.exception))

    def test_a_declined_move_stops_init(self) -> None:
        work_dir = self.home / ".claude-work"
        self.loom.registry.add_config_dir(work_dir, ClaudeCode.NAME)
        self.loom.registry.add_target_dir(work_dir, self.target_dir, [SOURCE])
        with (
            patch("loomwork.cli.prompts.can_ask", return_value=True),
            patch("loomwork.cli.prompts.confirm", return_value=False),
            self.assertRaises(LoomError) as refused,
        ):
            self.interview._confirm_moves(self.claude)
        self.assertEqual(refused.exception.code, "move_declined")

    def test_a_target_dir_wired_from_the_chosen_dir_needs_no_move(self) -> None:
        self.loom.registry.add_config_dir(self.claude_dir, ClaudeCode.NAME)
        self.loom.registry.add_target_dir(self.claude_dir, self.target_dir, [SOURCE])
        self.interview._confirm_moves(self.claude)

    def test_an_unsupported_agent_flag_is_refused(self) -> None:
        interview = InitInterview(self.loom, self.target_dir, agent_names="claude,cursor", source=None)
        with self.assertRaises(LoomError) as refused:
            interview._wanted_agents()
        self.assertEqual(refused.exception.code, "unsupported_agent")

    def test_the_source_prompt_shows_what_to_fix(self) -> None:
        self.assertEqual(self.interview._source_check(""), "a checkout path, or <host>/<owner>/<repo>")
        self.assertTrue(self.interview._source_check("forge.test/acme/rules"))

    def test_an_undeclared_target_dir_is_asked_what_it_takes(self) -> None:
        self.target_dir.mkdir()
        with (
            patch("loomwork.cli.prompts.can_ask", return_value=True),
            patch("loomwork.cli.prompts.confirm", return_value=True),
            patch("loomwork.cli.prompts.ask", return_value=SOURCE),
            patch("loomwork.cli.prompts.pick", side_effect=[("python",), ("translate",)]),
            patch("loomwork.sources.source.Source.fetch", return_value=make_clone(self.root, "offered")),
        ):
            declaration = self.interview._wanted_declaration()
        self.assertEqual(declaration.sources[0].source, SOURCE)
        self.assertEqual((declaration.rules, declaration.skills), (("python",), ("translate",)))
        # the target dir stays untouched while init is still asking
        self.assertFalse((self.target_dir / Declaration.FILE_NAME).exists())

    def test_the_offered_source_is_recorded_so_wiring_fetches_it_no_more(self) -> None:
        self.target_dir.mkdir()
        offered = make_clone(self.root, "offered")
        fetch = leaving_a_mark("fetched", result=False)
        with patch("loomwork.sources.source.Source.fetch", side_effect=lambda: fetch(offered) or offered):
            self.loom.sources.offered_by("forge.test/acme/offered")
            declare(self.target_dir, ("python",), source="forge.test/acme/offered")
            self.loom.sources.add_declared(self.target_dir)
        self.assertEqual(times_marked(offered, "fetched"), 1)
        self.assertEqual(self.loom.registry.checkout_of("forge.test/acme/offered"), offered)

    def test_a_declared_target_dir_is_asked_nothing_about_it(self) -> None:
        self.target_dir.mkdir()
        declare(self.target_dir, ("python",))
        with patch("loomwork.cli.prompts.confirm", side_effect=AssertionError("asked")):
            self.assertIsNone(self.interview._wanted_declaration())

    def test_without_a_terminal_the_recorded_agents_are_kept(self) -> None:
        self.loom.registry.add_config_dir(self.claude_dir, ClaudeCode.NAME)
        self.loom.registry.add_target_dir(self.claude_dir, self.target_dir, [SOURCE])
        with (
            patch("loomwork.cli.prompts.can_ask", return_value=False),
            patch.object(Agent, "is_present", return_value=False),
        ):
            self.assertEqual([agent.NAME for agent in self.interview._wanted_agents()], [ClaudeCode.NAME])

    def test_without_a_terminal_and_nothing_to_go_by_init_is_refused(self) -> None:
        with (
            patch("loomwork.cli.prompts.can_ask", return_value=False),
            patch.object(Agent, "is_present", return_value=False),
            self.assertRaises(LoomError) as refused,
        ):
            self.interview._wanted_agents()
        self.assertEqual(refused.exception.code, "no_agents")

    def test_a_relative_source_counts_from_the_target_dir(self) -> None:
        self.target_dir.mkdir()
        (self.target_dir / "rules-here").mkdir()
        self.assertTrue(self.interview._source_check("./rules-here"))
