from __future__ import annotations

import fcntl
import os
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import TYPE_CHECKING

from loomwork import COMMAND_NAME

if TYPE_CHECKING:
    from collections.abc import Iterator

# the folder in a target dir that holds loom's copies of its rules and skills, named by the .agents standard
AGENTS_DIR_NAME = ".agents"
# the universal layer every agent may read, by the same standard
AGENTS_MD_NAME = "AGENTS.md"
# loom's own dotfolder: its state, and the clones it fetches
HOME_DIR = Path(f"~/.{COMMAND_NAME}").expanduser()
SOURCES_DIR = HOME_DIR / "sources"


def target_rules_dir(target_dir: Path) -> Path:
    return target_dir / AGENTS_DIR_NAME / "rules"


def target_skills_dir(target_dir: Path) -> Path:
    return target_dir / AGENTS_DIR_NAME / "skills"


def link_target(target: Path, from_dir: Path) -> str:
    """target as a path relative to from_dir, so a link using it resolves inside the target dir wherever that is checked out."""
    return os.path.relpath(target, from_dir)


def as_path(location: str) -> Path | None:
    """The path a source location names when it is written as one — /…, ~…, ./… — rather than as a repo."""
    if not location.startswith(("/", "~", ".")):
        return None
    return Path(location).expanduser()


def resolved_from(location: str, base: Path) -> str:
    """A relative path made absolute from base; any other location, an absolute path or a repo, as it is."""
    named = as_path(location)
    if named is None or named.is_absolute():
        return location
    return str((base / named).resolve())


def shown(path: Path, inside: Path | None = None) -> str:
    """A path written the way its reader knows it — from the target dir it sits in, or from home."""
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
