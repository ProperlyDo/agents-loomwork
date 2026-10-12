from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from loomwork.registry import Registry


class RegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(lambda: __import__("shutil").rmtree(self.root, ignore_errors=True))
        self.registry = Registry(path=self.root / ".loomwork.json")

    def test_a_fresh_machine_reads_as_empty(self) -> None:
        self.assertIsNone(self.registry.source)
        self.assertIsNone(self.registry.namespace)
        self.assertEqual(self.registry.projects, [])

    def test_the_source_survives_a_reread(self) -> None:
        self.registry.remember_source(self.root / "agent-rules", "acme")
        self.assertEqual(self.registry.source, self.root / "agent-rules")
        self.assertEqual(self.registry.namespace, "acme")

    def test_every_name_the_machine_wired_under_is_kept(self) -> None:
        self.registry.remember_source(self.root / "agent-rules", "rh")
        self.registry.remember_source(self.root / "agent-rules", "regiohelden")
        self.registry.remember_namespace("regiohelden")
        self.assertEqual(self.registry.namespaces, ["rh", "regiohelden"])
        self.assertEqual(self.registry.namespace, "regiohelden")

    def test_projects_are_added_once(self) -> None:
        project = self.root / "project"
        self.assertTrue(self.registry.add(project))
        self.assertFalse(self.registry.add(project))
        self.assertEqual(self.registry.projects, [project])

    def test_dropping_reports_whether_it_was_known(self) -> None:
        project = self.root / "project"
        self.registry.add(project)
        self.assertTrue(self.registry.drop(project))
        self.assertFalse(self.registry.drop(project))
        self.assertEqual(self.registry.projects, [])

    def test_remembering_a_source_keeps_the_projects(self) -> None:
        project = self.root / "project"
        self.registry.add(project)
        self.registry.remember_source(self.root / "agent-rules", "acme")
        self.assertEqual(self.registry.projects, [project])


if __name__ == "__main__":
    unittest.main()
