from __future__ import annotations

import filecmp
import os
import shutil
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from loomwork import PACKAGE_NAME, paths
from loomwork.output import warn

if TYPE_CHECKING:
    from loomwork.registry import Registry
    from loomwork.sources import Catalog


def _is_identical_copy(source: Path, destination: Path) -> bool:
    """Whether destination holds exactly the files of source, with the same contents."""
    if not destination.is_dir():
        return False
    carried = {file.relative_to(source) for file in source.rglob("*") if file.is_file()}
    placed = {file.relative_to(destination) for file in destination.rglob("*") if file.is_file()}
    if carried != placed:
        return False
    return all(filecmp.cmp(source / name, destination / name) for name in carried)


@dataclass(frozen=True)
class Installation:
    """The file work loom does for every agent: copies, links, and clearing what it owns."""

    # what the sources added to this profile define
    catalog: Catalog
    # what we placed, since a directory is shared with whatever else installs there
    registry: Registry
    # the directories place() changed, for the caller to announce
    updated: list[Path] = field(default_factory=list)

    # trailing, so the rule's own frontmatter keeps line one
    COPY_MARKER: ClassVar[str] = f"<!-- written by {PACKAGE_NAME} -->"

    def place(self, wanted: dict[str, Path], into_dir: Path) -> tuple[str, ...]:
        """Copy each wanted rule file or skill folder into the directory, clear ours no longer wanted, and return the names that landed."""
        if not wanted and not into_dir.is_dir():
            return ()
        into_dir.mkdir(parents=True, exist_ok=True)
        # two sessions starting at once would otherwise copy into the same folder together
        with paths.locked(into_dir):
            landing = {
                name: original
                for name, original in wanted.items()
                if not self._unowned_exists(into_dir / original.name)
            }
            entry_names = {original.name for original in landing.values()}
            # recorded before copying, so a copy cut short is still ours to redo
            self.registry.record_owned_in(into_dir, [*self.registry.owned_in(into_dir), *entry_names])
            changed = False
            for original in landing.values():
                destination = into_dir / original.name
                if original.is_dir():
                    changed |= self._copy_folder(original, destination)
                else:
                    changed |= self._copy_file(original, destination)
            changed |= self.clear_owned_in(into_dir, keep=entry_names)
        if changed:
            self.updated.append(into_dir)
        return tuple(landing)

    def place_links(self, targets: dict[str, str], into_dir: Path) -> None:
        """Lay a link under each name, and clear the owned links no longer wanted."""
        into_dir.mkdir(parents=True, exist_ok=True)
        for name, target in targets.items():
            self.symlink(target, into_dir / name)
        self.clear_owned_in(into_dir, keep=set(targets))

    def place_file(self, original: Path, destination: Path) -> bool:
        """Copy one rule file to destination with our marker, unless something not owned is there. True when it now reads differently."""
        if self._unowned_exists(destination):
            return False
        return self._copy_file(original, destination)

    def symlink(self, target: Path | str, link_path: Path) -> bool:  # argument order mirrors ln -s
        """Link link_path to target, unless something not owned is there. True when the link now points somewhere new."""
        if self._unowned_exists(link_path):
            return False
        # read before the unlink below erases it
        was = str(link_path.readlink()) if link_path.is_symlink() else None
        link_path.unlink(missing_ok=True)
        # a concurrent sync may win the unlink-to-create window, and its link is identical
        with suppress(FileExistsError):
            link_path.symlink_to(target)
        return was != str(target)

    def clear_owned_in(self, directory: Path, keep: set[str] | None = None) -> bool:
        """Delete the owned files, folders and links directly in directory, except the names in keep. True when something went."""
        keep = keep or set()
        if not directory.is_dir():
            return False
        cleared = False
        for entry in list(directory.iterdir()):
            if not self.owned(entry) or entry.name in keep:
                continue
            if entry.is_dir() and not entry.is_symlink():
                shutil.rmtree(entry)
            else:
                entry.unlink(missing_ok=True)
            cleared = True
        # the record keeps only what is still there
        recorded = self.registry.owned_in(directory)
        self.registry.record_owned_in(directory, [name for name in recorded if (directory / name).exists()])
        return cleared

    def owned(self, path: Path) -> bool:
        """Ours when it is a link aiming where we lay them, recorded as placed by us, or a file with our marker."""
        if path.is_symlink():
            return self._is_owned_link(path)
        if path.name in self.registry.owned_in(path.parent):
            return True
        return path.is_file() and self._is_owned_copy(path)

    def _unowned_exists(self, path: Path) -> bool:
        """Whether something not owned exists at path — warned about, since it is then left alone."""
        taken = path.exists() or path.is_symlink()
        if taken and not self.owned(path):
            warn(f"{path} exists and is not ours — skipped")
            return True
        return False

    def _copy_folder(self, original: Path, destination: Path) -> bool:
        """Copy a skill folder over whatever of ours was there. True when it changed."""
        if _is_identical_copy(original, destination):
            return False
        shutil.rmtree(destination, ignore_errors=True)
        shutil.copytree(original, destination)
        return True

    def _copy_file(self, original: Path, destination: Path) -> bool:
        """Write a rule's text to destination with our marker. True when it now reads differently."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        rule = f"{self._unmarked(original)}\n\n{self.COPY_MARKER}\n".encode()
        # a link was never content, so replacing one always counts as changed
        was = None
        if destination.is_file() and not destination.is_symlink():
            was = destination.read_bytes()
        # unlink before writing — a stale link here would send the write into the clone
        destination.unlink(missing_ok=True)
        destination.write_bytes(rule)
        return was != rule

    def _unmarked(self, original: Path) -> str:
        """A rule's text without our marker, so a copy taken from a copy never carries two."""
        return original.read_text().rstrip().removesuffix(self.COPY_MARKER).rstrip()

    def _is_owned_link(self, link: Path) -> bool:
        """Owned links aim into the .agents/ of a directory that holds the link, or at the AGENTS.md beside it."""
        aimed = Path(os.path.normpath(link.parent / link.readlink()))
        if aimed.is_relative_to(Path.home() / paths.AGENTS_DIR_NAME):
            # home holds every project, but its own .agents/ is no project's
            return False
        return any(
            aimed.is_relative_to(root / paths.AGENTS_DIR_NAME) or aimed == root / "AGENTS.md" for root in link.parents
        )

    def _is_owned_copy(self, path: Path) -> bool:
        """Whether the file ends with our marker."""
        try:
            content = path.read_text(errors="replace")
        except OSError:
            return False
        return content.rstrip().endswith(self.COPY_MARKER)
