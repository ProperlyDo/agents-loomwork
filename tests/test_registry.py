from __future__ import annotations

import json

from tests.fixtures import SandboxTestCase


class RegistryTests(SandboxTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.registry = self.loom.registry

    def test_a_fresh_profile_reads_as_empty(self) -> None:
        self.assertEqual(self.registry.sources, [])
        self.assertEqual(self.registry.projects, [])

    def test_what_is_owned_is_found_however_the_directory_is_spelled(self) -> None:
        directory = self.root / "skills"
        directory.mkdir()
        (self.root / "via-link").symlink_to(directory)
        self.registry.record_owned_in(self.root / "via-link", ["translate", "translate"])
        self.assertEqual(self.registry.owned_in(directory), ["translate"])

    def test_records_of_directories_that_are_gone_are_dropped(self) -> None:
        gone = self.root / "deleted-project"
        gone.mkdir()
        self.registry.record_owned_in(gone, ["translate"])
        gone.rmdir()
        kept = self.root / "skills"
        kept.mkdir()
        self.registry.record_owned_in(kept, ["translate"])
        self.assertEqual(list(json.loads(self.registry.path.read_text())["owned"]), [str(kept)])

    def test_the_source_survives_a_reread(self) -> None:
        self.registry.add_source(
            "forge.test/acme/agent-rules", self.root / "agent-rules", "forge.test/acme/agent-rules"
        )
        self.assertEqual(self.registry.added_sources, [(self.root / "agent-rules", "forge.test/acme/agent-rules")])
        self.assertEqual(self.registry.source_for("forge.test/acme/agent-rules"), self.root / "agent-rules")

    def test_sources_keep_the_order_they_were_added(self) -> None:
        # a later source wins a filename, so the order is what decides a clash
        self.registry.add_source("forge.test/one/rules", self.root / "one", "forge.test/one/rules")
        self.registry.add_source("forge.test/two/rules", self.root / "two", "forge.test/two/rules")
        self.assertEqual(self.registry.sources, [self.root / "one", self.root / "two"])

    def test_adding_the_same_source_again_moves_it_to_the_end(self) -> None:
        self.registry.add_source("forge.test/one/rules", self.root / "one", "forge.test/one/rules")
        self.registry.add_source("forge.test/two/rules", self.root / "two", "forge.test/two/rules")
        self.registry.add_source("forge.test/one/rules", self.root / "moved", "forge.test/one/rules")
        self.assertEqual(self.registry.sources, [self.root / "two", self.root / "moved"])

    def test_a_file_from_another_shape_reads_as_empty(self) -> None:
        # whatever wrote it, loom must start rather than raise on a key it does not know
        self.registry.path.parent.mkdir(parents=True)
        self.registry.path.write_text('{"version": 1, "source": {"path": "/somewhere"}, "namespace": "acme"}')
        self.assertEqual(self.registry.sources, [])
        self.assertEqual(self.registry.projects, [])

    def test_projects_are_added_once(self) -> None:
        project = self.root / "project"
        self.registry.add_project(project, [])
        self.registry.add_project(project, ["claude"])
        self.assertEqual(self.registry.projects, [project])
        self.assertEqual(self.registry.agents_for(project), ["claude"])

    def test_a_project_is_one_entry_however_its_path_is_spelled(self) -> None:
        project = self.root / "project"
        project.mkdir()
        (self.root / "via-link").symlink_to(project)
        self.registry.add_project(self.root / "via-link", ["claude"])
        self.assertTrue(self.registry.knows_project(project))
        self.assertEqual(self.registry.projects, [project])

    def test_dropping_reports_whether_it_was_known(self) -> None:
        project = self.root / "project"
        self.registry.add_project(project, [])
        self.assertTrue(self.registry.drop_project(project))
        self.assertFalse(self.registry.drop_project(project))
        self.assertEqual(self.registry.projects, [])

    def test_adding_a_source_keeps_the_projects(self) -> None:
        project = self.root / "project"
        self.registry.add_project(project, [])
        self.registry.add_source(
            "forge.test/acme/agent-rules", self.root / "agent-rules", "forge.test/acme/agent-rules"
        )
        self.assertEqual(self.registry.projects, [project])
