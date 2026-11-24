from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

from loomwork import git
from tests.fixtures import SandboxTestCase

if TYPE_CHECKING:
    from pathlib import Path


class MatchRemoteTests(SandboxTestCase):
    def test_nothing_is_reset_when_the_fetch_fails(self) -> None:
        def failing_fetch(*arguments: str, inside: Path | None = None, timeout: float | None = None) -> None:  # noqa: ARG001
            if "reset" in arguments:
                (self.root / "reset").touch()

        with patch("loomwork.git.run", side_effect=failing_fetch):
            self.assertFalse(git.match_remote(self.root))
        self.assertFalse((self.root / "reset").exists())
