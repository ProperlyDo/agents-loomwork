from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import patch

from loomwork.agents import ClaudeCode, OpenCode
from loomwork.declaration import Declaration, DeclaredSource, Manifest
from loomwork.loom import Loom
from loomwork.questions import valid_directory, valid_source, wanted_config_dir
from loomwork.registry import Registry
from tests.fixtures import SOURCE, SandboxTestCase, make_clone, make_project


class ProfileTests(SandboxTestCase):
    """What a profile is: the registry in its config dir, and the sources added to it."""

    def test_without_a_source_it_says_what_to_run(self) -> None:
        with self.assertRaises(SystemExit):
            self.loom.installation()

    def test_the_source_added_to_this_profile_is_what_acts(self) -> None:
        clone = make_clone(self.root, "clone")
        self.loom.registry.add_source("forge.test/acme/rules", clone, "forge.test/acme/rules")
        self.assertEqual(self.loom.installation().catalog.rules["python"], clone / "rules" / "python.md")

    def test_it_sits_in_the_config_dir_it_was_given(self) -> None:
        work = self.root / "home" / ".claude-work"
        self.assertEqual(Loom(work).registry.path, work / Registry.FILE_NAME)
        self.assertEqual(Loom(work).agents_named(("claude",))[0].config_dir, work)


class RegistryFollowsWiringTests(SandboxTestCase):
    """Whatever wires a project records it — a hook-driven sync counts as much as a hand-typed init."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project(self.root)
        self.loom.registry.add_source(SOURCE, make_clone(self.root), SOURCE)
        self.enterContext(patch("loomwork.git.pull", return_value=True))

    def test_a_hook_driven_sync_records_the_project_with_the_agent_that_asked(self) -> None:
        # without the agent, every later sync would wire none — a skill added later would never reach Claude
        self.loom.sync(self.project, "claude")
        self.assertEqual(self.loom.registry.projects, [self.project])
        self.assertEqual(self.loom.registry.agents_for(self.project), ["claude"])

    def test_an_agent_left_out_of_a_new_choice_is_unwired(self) -> None:
        self.loom.add(self.project, ("claude", "opencode"))
        self.assertTrue((self.project / ".claude" / "rules" / "loom").is_symlink())
        self.loom.add(self.project, ("opencode",))
        self.assertFalse((self.project / ".claude").exists())
        self.assertEqual(self.loom.registry.agents_for(self.project), ["opencode"])

    def test_removing_a_project_takes_its_skills_but_not_foreign_ones(self) -> None:
        (self.project / Declaration.FILE_NAME).write_text(
            f'source = "{SOURCE}"\nrules = ["python"]\nskills = ["translate"]\n'
        )
        theirs = self.project / ".agents" / "skills" / "from-the-cli"
        theirs.mkdir(parents=True)
        self.loom.add(self.project, ("claude",))
        self.assertTrue((self.project / ".agents" / "skills" / "translate" / "SKILL.md").is_file())
        self.loom.remove(self.project)
        self.assertFalse((self.project / ".agents" / "skills" / "translate").exists())
        self.assertTrue(theirs.is_dir())

    def test_uninstall_unbridges_an_agent_that_is_not_installed(self) -> None:
        self.loom.add(self.project, ("opencode",))
        agents_md = OpenCode().config_dir / "AGENTS.md"
        self.assertTrue(agents_md.is_file())
        with patch("shutil.which", return_value=None):
            self.loom.uninstall()
        self.assertFalse(agents_md.exists())

    def test_a_session_of_another_agent_adds_to_what_was_chosen(self) -> None:
        self.loom.registry.add_project(self.project, ["opencode"])
        self.loom.sync(self.project, "claude")
        self.assertEqual(self.loom.registry.agents_for(self.project), ["claude", "opencode"])

    def test_a_sync_that_changed_something_asks_for_one_restart(self) -> None:
        said = self.stdout_of(lambda: self.loom.sync(self.project, "claude"))
        self.assertEqual(said.count("restart any open session"), 1)

    def test_a_sync_that_changed_nothing_asks_for_no_restart(self) -> None:
        self.loom.sync(self.project, "claude")
        self.assertNotIn("restart", self.stdout_of(lambda: self.loom.sync(self.project, "claude")))

    def test_init_asks_for_no_restart(self) -> None:
        # no session is open yet to restart
        def first_init() -> None:
            self.loom.init(self.project, ("claude",))
            self.loom.add(self.project, ("claude",))

        self.assertNotIn("restart", self.stdout_of(first_init))

    def test_a_project_that_dropped_its_declaration_is_forgotten(self) -> None:
        self.loom.sync(self.project)
        (self.project / Declaration.FILE_NAME).unlink()
        self.loom.sync(self.project)
        self.assertEqual(self.loom.registry.projects, [])


class AddedSourcesTests(SandboxTestCase):
    """A source may build on others: the same [[source]] blocks, meaning 'I build on this' in a source's own file."""

    def setUp(self) -> None:
        super().setUp()
        self.base = make_clone(self.root, "base-rules")
        self.team = make_clone(self.root, "team-rules")
        # local checkouts that were never pushed
        self.enterContext(patch("loomwork.git.origin", return_value=None))

    def builds_on(self, source: Path, base: Path) -> None:
        (source / Manifest.FILE_NAME).write_text(f'[[source]]\nsource = "{base}"\n')

    def test_adding_a_source_says_where_it_sits(self) -> None:
        self.assertEqual(self.loom.add_source(str(self.team)), self.team)

    def test_what_a_source_builds_on_comes_first(self) -> None:
        # broadest first, so the source that declared the dependency wins a shared filename
        self.builds_on(self.team, self.base)
        self.loom.add_source(str(self.team))
        self.assertEqual(self.loom.registry.sources, [self.base, self.team])

    def test_a_cycle_is_added_once(self) -> None:
        self.builds_on(self.team, self.base)
        self.builds_on(self.base, self.team)
        self.loom.add_source(str(self.team))
        self.assertEqual(sorted(self.loom.registry.sources), sorted([self.base, self.team]))


class RefreshTests(SandboxTestCase):
    """Every source is updated before a sync copies from it."""

    def setUp(self) -> None:
        super().setUp()
        for name in ("one", "two"):
            (self.root / name).mkdir()
            self.loom.registry.add_source(f"forge.test/{name}/rules", self.root / name, f"forge.test/{name}/rules")

    def test_a_refresh_updates_every_source(self) -> None:
        with patch("loomwork.git.pull", return_value=True) as pulled:
            self.loom.refresh()
        self.assertEqual({call.args[0].name for call in pulled.call_args_list}, {"one", "two"})

    def test_two_sources_in_one_repo_update_it_once(self) -> None:
        repo = self.root / "big-repo"
        (repo / ".git").mkdir(parents=True)
        for name in ("agents", "skills-only"):
            (repo / name).mkdir()
            self.loom.registry.add_source(f"forge.test/big/{name}", repo / name, f"forge.test/big/{name}")
        with patch("loomwork.git.pull", return_value=True) as pulled:
            self.loom.refresh()
        self.assertEqual([call.args[0] for call in pulled.call_args_list].count(repo), 1)


class ChosenAgentsTests(SandboxTestCase):
    """Which agents a project is wired for: what it was set up for, plus the agent asking."""

    def setUp(self) -> None:
        super().setUp()
        self.project = self.root / "project"

    def test_choosing_no_agents_wires_none_rather_than_all(self) -> None:
        # an empty choice is an answer, not a reason to fall back to everything installed
        self.loom.registry.add_project(self.project, [])
        self.assertEqual(self.loom.agents_for(self.project), ())

    def test_a_recorded_choice_is_what_gets_wired(self) -> None:
        self.loom.registry.add_project(self.project, ["opencode"])
        self.assertEqual([agent.NAME for agent in self.loom.agents_for(self.project)], ["opencode"])

    def test_a_project_nobody_chose_for_gets_the_agent_that_asked(self) -> None:
        # the session hook names itself, and loom wires that agent only — never everything installed
        self.assertEqual([agent.NAME for agent in self.loom.agents_for(self.project, "claude")], ["claude"])

    def test_a_project_nobody_chose_for_and_nobody_asked_about_gets_nothing(self) -> None:
        self.assertEqual(self.loom.agents_for(self.project), ())

    def test_the_recorded_choice_is_what_init_offers_ticked(self) -> None:
        self.loom.registry.add_project(self.project, ["opencode"])
        self.assertEqual(self.loom.usual_agents(self.project), ("opencode",))

    def test_a_new_project_is_offered_what_is_installed(self) -> None:
        with patch("shutil.which", side_effect=lambda command: command == "claude"):
            self.assertIn("claude", self.loom.usual_agents(self.project))
            self.assertNotIn("opencode", self.loom.usual_agents(self.project))


class DeclaredSourceTests(SandboxTestCase):
    """A project naming a source this profile lacks is what makes loom fetch it, even beside one it has."""

    def setUp(self) -> None:
        super().setUp()
        self.clone = make_clone(self.root, "acme-rules")
        self.loom.registry.add_source(SOURCE, self.clone, SOURCE)

    def test_a_source_already_added_is_never_fetched(self) -> None:
        project = make_project(self.root)
        with patch("loomwork.sources.fetch", side_effect=AssertionError("should not clone")):
            self.loom.add_declared_sources(project)

    def test_an_unknown_source_is_fetched_even_beside_a_known_one(self) -> None:
        project = make_project(self.root, source="forge.test/other/rules")
        fetched = make_clone(self.root, "other-rules")
        with patch("loomwork.sources.fetch", return_value=fetched):
            self.loom.add_declared_sources(project)
        self.assertIn(fetched, self.loom.registry.sources)

    def test_a_source_whose_clone_is_gone_is_fetched_again(self) -> None:
        shutil.rmtree(self.clone)
        project = make_project(self.root)
        fetched = make_clone(self.root, "fetched-again")
        with patch("loomwork.sources.fetch", return_value=fetched):
            self.loom.add_declared_sources(project)
        self.assertEqual(self.loom.registry.source_for(SOURCE), fetched)

    def test_a_checkout_of_a_cloned_repo_replaces_the_clone(self) -> None:
        # one repo, two spellings: the project names the working copy, the profile holds a fetched clone
        checkout = make_clone(self.root, "rules-checkout")
        project = make_project(self.root, source=str(checkout))
        with patch("loomwork.sources.identity", return_value=SOURCE):
            self.loom.add_declared_sources(project)
        self.assertEqual(self.loom.registry.source_for(SOURCE), checkout)

    def test_a_relative_path_counts_from_the_project(self) -> None:
        sibling = make_clone(self.root, "sibling-rules")
        project = make_project(self.root, source="../sibling-rules")
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        with patch("os.getcwd", return_value=str(elsewhere)), patch("loomwork.git.origin", return_value=None):
            self.loom.add_declared_sources(project)
        self.assertIn(sibling, self.loom.registry.sources)

    def test_init_places_the_global_skills_in_the_same_run(self) -> None:
        (self.clone / Manifest.FILE_NAME).write_text('[global]\nskills = ["translate"]\n')
        project = make_project(self.root)
        self.loom.init(project, ("claude",))
        self.assertTrue((self.loom.config_dir / "skills" / "translate" / "SKILL.md").is_file())

    def test_init_takes_the_source_from_what_the_project_declares(self) -> None:
        # the first teammate on a fresh machine has a committed declaration and should be asked nothing
        project = make_project(self.root, source="forge.test/other/rules")
        fetched = make_clone(self.root, "other-rules")
        with patch("loomwork.sources.fetch", return_value=fetched):
            self.loom.init(project, ())
        self.assertIn(fetched, self.loom.registry.sources)


class ReportingTests(SandboxTestCase):
    """What status and sync tell the user."""

    def setUp(self) -> None:
        super().setUp()
        self.clone = make_clone(self.root)
        self.loom.registry.add_source(SOURCE, self.clone, SOURCE)

    def test_a_cloned_source_that_is_gone_says_how_to_fetch_it_again(self) -> None:
        shutil.rmtree(self.clone)
        said = self.stderr_of(self.loom.refresh)
        self.assertIn(f"source {SOURCE} is gone", said)
        self.assertIn(f"init --source {SOURCE}", said)
        self.assertNotIn("could not update", said)

    def test_a_checkout_that_is_gone_asks_where_it_lives_now(self) -> None:
        checkout = make_clone(self.root, "my-rules")
        self.loom.registry.add_source(str(checkout), checkout, str(checkout))
        shutil.rmtree(checkout)
        with patch("loomwork.git.pull", return_value=True):
            said = self.stderr_of(self.loom.refresh)
        self.assertIn(f"source {checkout} is gone — point", said)

    def test_status_names_what_every_project_gets_anyway(self) -> None:
        # no project's declaration mentions them, so status is the only place they are visible
        self.assertIn("every project gets rules: git", self.stdout_of(self.loom.status))

    def test_syncing_an_undeclared_project_says_so(self) -> None:
        bare = self.root / "bare"
        bare.mkdir()
        self.assertIn("nothing to sync", self.stderr_of(lambda: self.loom.sync(bare)))


class QuestionnaireTests(SandboxTestCase):
    """What init asks, what it stops asking once the answer is recorded, and what it says when an answer is refused."""

    def setUp(self) -> None:
        super().setUp()
        self.loom.registry.add_source(SOURCE, make_clone(self.root), SOURCE)
        self.project = self.root / "project"

    def test_a_project_the_default_profile_knows_is_not_asked_where_its_config_sits(self) -> None:
        self.loom.registry.add_project(self.project, [])
        with (
            patch.object(ClaudeCode, "DEFAULT_CONFIG_DIR", self.loom.config_dir),
            patch("sys.stdin.isatty", return_value=True),
        ):
            self.assertEqual(wanted_config_dir(None, self.project), self.loom.config_dir)

    def test_the_flag_is_taken_as_given(self) -> None:
        work = self.root / "home" / ".claude-work"
        self.assertEqual(wanted_config_dir(work, self.project), work)

    def test_a_source_says_what_it_wants(self) -> None:
        self.assertEqual(valid_source(""), "a checkout path, or <host>/<owner>/<repo>")
        self.assertIn("is no <host>/<owner>/<repo>", valid_source("not a repo"))
        self.assertTrue(valid_source("forge.test/acme/rules"))

    def test_a_config_dir_says_what_it_wants(self) -> None:
        self.assertIn("a directory path", valid_directory(""))
        self.assertIn("absolute path", valid_directory("relative/dir"))
        self.assertTrue(valid_directory("~/.claude-work"))

    def test_gitignore_covers_every_agents_folders(self) -> None:
        self.assertEqual(self.loom.generated, (".agents/", ".claude/"))

    def test_the_default_source_is_the_one_most_projects_declare(self) -> None:
        for name in ("one", "two"):
            project = self.root / name
            project.mkdir()
            Declaration((DeclaredSource(SOURCE, ("python",)),)).write(project)
            self.loom.registry.add_project(project, [])
        odd = self.root / "odd"
        odd.mkdir()
        Declaration((DeclaredSource("forge.test/other/rules", ()),)).write(odd)
        self.loom.registry.add_project(odd, [])

        self.assertEqual(self.loom.most_declared_source(), SOURCE)


class DeclarationTests(SandboxTestCase):
    def test_a_broken_declaration_fails_in_one_line(self) -> None:
        project = make_project(self.root)
        (project / Declaration.FILE_NAME).write_text("source = \n")
        said = self.stderr_of(lambda: self.assertRaises(SystemExit, Declaration.read, project))
        self.assertEqual(len(said.splitlines()), 1)
