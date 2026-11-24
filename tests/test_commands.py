from __future__ import annotations

from unittest.mock import patch

from click.testing import CliRunner

from loomwork.cli.commands import cli
from tests.fixtures import SandboxTestCase, make_target_dir


class CommandsTests(SandboxTestCase):
    """What the command line does with what loom refuses, and with what it was given."""

    def setUp(self) -> None:
        super().setUp()
        self.enterContext(patch("loomwork.paths.HOME_DIR", self.home / ".loom"))
        self.runner = CliRunner()

    def test_a_refusal_prints_one_error_line_and_exits_1(self) -> None:
        target_dir = make_target_dir(self.root)
        result = self.runner.invoke(cli, ["sync", "--for", "cursor", str(target_dir)])
        self.assertEqual(result.exit_code, 1)
        self.assertIn("ERROR unsupported: cursor.", result.output)

    def test_init_refuses_a_target_dir_that_does_not_exist(self) -> None:
        result = self.runner.invoke(cli, ["init", str(self.root / "missing"), "--agents", "claude"])
        self.assertEqual(result.exit_code, 2)
        self.assertIn("does not exist", result.output)
