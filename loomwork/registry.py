from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from loomwork import PACKAGE_NAME, paths


@dataclass(frozen=True)
class Registry:
    """What one profile knows: the sources added to it, the projects it wired, and what it owns where."""

    FILE_NAME: ClassVar[str] = f".{PACKAGE_NAME}.json"

    path: Path

    def add_source(self, key: str, path: Path, given: str) -> None:
        """Add a source under its key, where it sits and how it was spelled — added again, it moves to the end and wins a shared name."""
        with self._changing() as state:
            state["sources"].pop(key, None)
            state["sources"][key] = {"path": str(path), "given": given}

    def source_for(self, key: str) -> Path | None:
        """Where the source filed under key sits — None when it was never added."""
        known = self._read()["sources"].get(key)
        if known is None:
            return None
        return Path(known["path"])

    @property
    def sources(self) -> list[Path]:
        """Where each source sits, in the order they were added — a later one wins a shared name."""
        return [path for path, given in self.added_sources]

    @property
    def added_sources(self) -> list[tuple[Path, str]]:
        """Each source in the order it was added: where it sits, and how it was spelled."""
        return [(Path(known["path"]), known["given"]) for known in self._read()["sources"].values()]

    def add_project(self, project_dir: Path, agents: list[str]) -> None:
        """Remember a project and the agents it is wired for."""
        with self._changing() as state:
            state["projects"][str(project_dir.resolve())] = agents

    def knows_project(self, project_dir: Path) -> bool:
        """Whether this project was ever wired — an empty choice of agents is an answer, not a silence."""
        return str(project_dir.resolve()) in self._read()["projects"]

    def agents_for(self, project_dir: Path) -> list[str]:
        """The agents this project is wired for — empty when it was never asked."""
        return self._read()["projects"].get(str(project_dir.resolve()), [])

    def drop_project(self, project_dir: Path) -> bool:
        """Forget a project; False when it was not known."""
        with self._changing() as state:
            return state["projects"].pop(str(project_dir.resolve()), None) is not None

    @property
    def projects(self) -> list[Path]:
        return [Path(project) for project in self._read()["projects"]]

    def owned_in(self, directory: Path) -> list[str]:
        """The names of the entries we own in a directory — the record for what cannot say so itself."""
        return self._read()["owned"].get(str(directory.resolve()), [])

    def record_owned_in(self, directory: Path, names: list[str]) -> None:
        """Replace the record of what we own in a directory, dropping the records of directories that are gone."""
        with self._changing() as state:
            owned = {key: entries for key, entries in state["owned"].items() if Path(key).is_dir()}
            if names:
                owned[str(directory.resolve())] = sorted(set(names))
            else:
                owned.pop(str(directory.resolve()), None)
            state["owned"] = owned

    def forget(self) -> None:
        """Delete everything this profile knows."""
        self.path.unlink(missing_ok=True)

    def _read(self) -> dict:
        """Our state, with every key present — a file of another shape reads as empty, not broken."""
        state: dict = {"sources": {}, "projects": {}, "owned": {}}
        written = self.path.read_text() if self.path.is_file() else ""
        # empty while a first change holds the lock on the file it just created
        if not written.strip():
            return state
        on_disk = json.loads(written)
        return state | {key: on_disk[key] for key in state if isinstance(on_disk.get(key), type(state[key]))}

    @contextmanager
    def _changing(self) -> Iterator[dict]:
        """Read, change and write under one lock: two sessions starting at once would otherwise lose a write."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch()
        with paths.locked(self.path):
            state = self._read()
            was = json.dumps(state, sort_keys=True)
            yield state
            if json.dumps(state, sort_keys=True) != was:
                self.path.write_text(json.dumps(state, indent=2) + "\n")
