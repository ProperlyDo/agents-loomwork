from __future__ import annotations

from loomwork.errors import LoomError
from loomwork.validators import validate_agent_names, validate_source
from tests.fixtures import SandboxTestCase


class ValidateSourceTests(SandboxTestCase):
    def assert_refused(self, location: str, code: str) -> None:
        with self.assertRaises(LoomError) as refused:
            validate_source(location)
        self.assertEqual(refused.exception.code, code)

    def test_an_empty_answer_is_refused(self) -> None:
        self.assert_refused("  ", "source_missing")

    def test_a_path_that_is_not_there_is_refused(self) -> None:
        self.assert_refused(str(self.root / "no-such-rules"), "no_such_directory")

    def test_a_location_that_is_no_repo_is_refused(self) -> None:
        self.assert_refused("not a repo", "not_a_repo_address")

    def test_a_repo_address_and_an_existing_dir_pass(self) -> None:
        validate_source("forge.test/acme/rules")
        validate_source(str(self.root))


class ValidateAgentNamesTests(SandboxTestCase):
    def test_a_name_loom_does_not_support_is_refused(self) -> None:
        with self.assertRaises(LoomError) as refused:
            validate_agent_names(("claude", "cursor"))
        self.assertEqual(refused.exception.code, "unsupported_agent")
        self.assertIn("unsupported: cursor.", str(refused.exception))
