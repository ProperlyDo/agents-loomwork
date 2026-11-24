from __future__ import annotations

import io
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

from loomwork.agents import SUPPORTED_AGENTS, ClaudeCode, OpenCode
from loomwork.installation import Installation
from loomwork.loom import Loom
from loomwork.registry import Registry
from loomwork.sources.catalog import Catalog
from loomwork.sources.manifest import Manifest
from loomwork.targets.declaration import Declaration

if TYPE_CHECKING:
    from collections.abc import Callable

# the source every fixture target dir declares, and the key its clone is filed under
SOURCE = "forge.test/acme/agent-rules"
# a second source, for what two of them do together
TEAM_SOURCE = "forge.test/team/rules"
DECLARED_RULE = "# Python\n"
GLOBAL_RULE = "# Git\n"


def make_clone(root: Path, name: str = "agents-config") -> Path:
    """A stand-in for a source: the universal layer, two rules a target dir may declare, a global one, and a skill."""
    clone = root / name
    (clone / "rules").mkdir(parents=True)
    (clone / "AGENTS.md").write_text("# Agent Instructions\n")
    (clone / "rules" / "python.md").write_text(DECLARED_RULE)
    (clone / "rules" / "django.md").write_text(DECLARED_RULE)
    (clone / "rules" / "git.md").write_text(GLOBAL_RULE)
    (clone / Manifest.FILE_NAME).write_text('[global]\nrules = ["git"]\n')
    (clone / "skills" / "translate").mkdir(parents=True)
    (clone / "skills" / "translate" / "SKILL.md").write_text("---\nname: translate\ndescription: fills catalogs\n---\n")
    return clone


def make_target_dir(
    root: Path, rules: tuple[str, ...] = ("python",), source: str = SOURCE, skills: tuple[str, ...] = ()
) -> Path:
    target_dir = root / "target_dir"
    target_dir.mkdir()
    (target_dir / "AGENTS.md").write_text("# Target dir\n")
    declare(target_dir, rules, source, skills)
    return target_dir


def leaving_a_mark(mark: str, result: bool = True) -> Callable[..., bool]:
    """A stand-in for a git update or a fetch: it adds a line to `mark` in the checkout, so a test sees where it ran."""

    def update(checkout: Path, *arguments: object) -> bool:  # noqa: ARG001
        with (checkout / mark).open("a") as marked:
            marked.write("ran\n")
        return result

    return update


def times_marked(checkout: Path, mark: str) -> int:
    if not (checkout / mark).is_file():
        return 0
    return len((checkout / mark).read_text().splitlines())


def declare(target_dir: Path, rules: tuple[str, ...], source: str = SOURCE, skills: tuple[str, ...] = ()) -> None:
    """The committed opt-in: which rules repo this target dir uses, and what it wants of it."""
    listed = ", ".join(f'"{name}"' for name in rules)
    wanted = ", ".join(f'"{name}"' for name in skills)
    (target_dir / Declaration.FILE_NAME).write_text(f'source = "{source}"\nrules = [{listed}]\nskills = [{wanted}]\n')


class SandboxTestCase(unittest.TestCase):
    """A temp root holding the home, loom's registry, the sources and the target dirs — nothing reaches the real home."""

    def setUp(self) -> None:
        # resolved, because ownership follows links to their end — /var and /private/var must not differ here
        self.root = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.home = self.root / "home"
        # every agent's standard dir follows HOME or XDG_CONFIG_HOME, which would otherwise be the real ones
        self.enterContext(
            patch.dict(os.environ, {"HOME": str(self.home), "XDG_CONFIG_HOME": str(self.home / ".config")})
        )
        # a session running these tests may itself be launched with another config dir
        for kind in SUPPORTED_AGENTS:
            os.environ.pop(kind.CONFIG_DIR_ENV, None)
        self.claude_dir = ClaudeCode.standard_config_dir()
        self.loom = Loom(Registry(self.home / ".loom" / Registry.FILE_NAME))
        # loom narrates every step — only the tests that assert on it want to read it
        self.enterContext(patch("sys.stdout", new_callable=io.StringIO))

    def stderr_of(self, action: Callable[[], object]) -> str:
        captured = io.StringIO()
        with redirect_stderr(captured):
            action()
        return captured.getvalue()

    def stdout_of(self, action: Callable[[], object]) -> str:
        captured = io.StringIO()
        with redirect_stdout(captured):
            action()
        return captured.getvalue()


class InstallationTestCase(SandboxTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.clone = make_clone(self.root)
        self.sources = (self.clone,)
        self.loom.registry.add_source(SOURCE, self.clone, SOURCE)

    @property
    def installation(self) -> Installation:
        """Built on every use, as loom does, so a source changed after setUp is read as it now is."""
        return Installation(catalog=Catalog.of(*self.sources), registry=self.loom.registry)


class WiredTargetDirTestCase(SandboxTestCase):
    """A declared target dir and its source, ready to be wired for Claude or OpenCode."""

    def setUp(self) -> None:
        super().setUp()
        self.target_dir = make_target_dir(self.root)
        self.loom.registry.add_source(SOURCE, make_clone(self.root), SOURCE)
        # the source is filed under its repo address, so an update takes the clone's way to the remote
        self.enterContext(patch("loomwork.git.match_remote", return_value=True))
        self.claude, self.opencode = self.loom.agents_named((ClaudeCode.NAME, OpenCode.NAME))
