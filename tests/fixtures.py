from __future__ import annotations

import io
import os
import shutil
import tempfile
import unittest
from collections.abc import Callable
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from loomwork.declaration import Declaration, Manifest
from loomwork.loom import Loom

# the source every fixture project declares, and the key its clone is filed under
SOURCE = "forge.test/acme/agent-rules"
DECLARED_RULE = "# Python\n"
GLOBAL_RULE = "# Git\n"


def make_clone(root: Path, name: str = "agents-config") -> Path:
    """A stand-in for a source: the universal layer, two rules a project may declare, a global one, and a skill."""
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


def make_project(
    root: Path, rules: tuple[str, ...] = ("python",), source: str = SOURCE, skills: tuple[str, ...] = ()
) -> Path:
    project = root / "project"
    project.mkdir()
    (project / "AGENTS.md").write_text("# Project\n")
    declare(project, rules, source, skills)
    return project


def declare(project: Path, rules: tuple[str, ...], source: str = SOURCE, skills: tuple[str, ...] = ()) -> None:
    """The committed opt-in: which rules repo this project uses, and what it wants of it."""
    listed = ", ".join(f'"{name}"' for name in rules)
    wanted = ", ".join(f'"{name}"' for name in skills)
    (project / Declaration.FILE_NAME).write_text(f'source = "{source}"\nrules = [{listed}]\nskills = [{wanted}]\n')


class SandboxTestCase(unittest.TestCase):
    """A temp root holding the profile, its sources and its projects — nothing reaches the real home."""

    def setUp(self) -> None:
        # resolved, because ownership follows links to their end — /var and /private/var must not differ here
        self.root = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        # handed to every ClaudeCode here, so nothing reaches the real ~/.claude
        self.claude_dir = self.root / "home" / ".claude"
        self.loom = Loom(self.claude_dir)
        # OpenCode's config dir follows XDG_CONFIG_HOME, which would otherwise be the real ~/.config
        self.enterContext(patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.root / "home" / ".config")}))
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
