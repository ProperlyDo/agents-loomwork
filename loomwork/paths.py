from __future__ import annotations

import fcntl
import os
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path

from loomwork import COMMAND_NAME

# the folder in a project that holds loom's copies of its rules and skills, named by the .agents standard
AGENTS_DIR_NAME = ".agents"
# the clones loom fetches, in a dotfolder of its own
SOURCES_DIR = Path(f"~/.{COMMAND_NAME}/sources").expanduser()


def project_rules_dir(project_dir: Path) -> Path:
    return project_dir / AGENTS_DIR_NAME / "rules"


def project_skills_dir(project_dir: Path) -> Path:
    return project_dir / AGENTS_DIR_NAME / "skills"


def link_target(target: Path, from_dir: Path) -> str:
    """target spelled from from_dir, so a link using it resolves inside the project wherever that is checked out."""
    return os.path.relpath(target, from_dir)


def as_path(spelled: str) -> Path | None:
    """The path a string names when it is spelled as one — /…, ~…, ./… — rather than as a repo."""
    if not spelled.startswith(("/", "~", ".")):
        return None
    return Path(spelled).expanduser()


def resolved_from(spelled: str, base: Path) -> str:
    """A relative path made absolute from base; any other spelling, an absolute path or a repo, as it is."""
    named = as_path(spelled)
    if named is None or named.is_absolute():
        return spelled
    return str((base / named).resolve())


def shown(path: Path, inside: Path | None = None) -> str:
    """A path spelled the way its reader knows it — from the project it sits in, or from home."""
    if inside and path.is_relative_to(inside):
        return str(path.relative_to(inside))
    home = Path.home()
    if path.is_relative_to(home):
        return f"~/{path.relative_to(home)}"
    return str(path)


def remove_if_empty(directory: Path) -> None:
    with suppress(OSError):
        directory.rmdir()


@contextmanager
def locked(path: Path) -> Iterator[None]:
    """Hold a file or directory for this process alone until the block ends — the kernel lets go if the process dies."""
    descriptor = os.open(path, os.O_RDONLY)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)
