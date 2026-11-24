from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from loomwork import PACKAGE_NAME, paths

if TYPE_CHECKING:
    from collections.abc import Iterator


@dataclass(frozen=True)
class Registry:
    """What loom knows on this machine: the sources it fetched, each agent dir it writes into, and what it owns where."""

    FILE_NAME: ClassVar[str] = f"{PACKAGE_NAME}.json"

    path: Path

    @classmethod
    def at_home(cls) -> Registry:
        return cls(paths.HOME_DIR / cls.FILE_NAME)

    def add_source(self, key: str, path: Path, source: str, builds_on: list[str] | None = None) -> None:
        """File a source under its key, with where it sits, how it was declared and the keys of what it builds on."""
        with self._changing() as state:
            state["sources"][key] = {"path": str(path), "source": source, "builds_on": builds_on or []}

    def add_config_dir(self, config_dir: Path, agent_name: str) -> None:
        """Remember a config dir as the named agent's, keeping what was recorded for it."""
        with self._changing() as state:
            state["config_dirs"].setdefault(
                self._key(config_dir), {"agent": agent_name, "pinned": [], "target_dirs": {}}
            )

    def pin_source(self, config_dir: Path, key: str) -> None:
        """Pin a source to a config dir, whatever its target dirs declare — pinned again, it moves to the end and wins a shared name."""
        with self._changing() as state:
            pinned = state["config_dirs"][self._key(config_dir)]["pinned"]
            if key in pinned:
                pinned.remove(key)
            pinned.append(key)

    def add_target_dir(self, config_dir: Path, target_dir: Path, declared: list[str]) -> None:
        """Remember that a target dir is wired from this config dir, with the keys of the sources it declares."""
        with self._changing() as state:
            state["config_dirs"][self._key(config_dir)]["target_dirs"][self._key(target_dir)] = declared

    def drop_target_dir(self, config_dir: Path, target_dir: Path) -> None:
        with self._changing() as state:
            target_dirs = state["config_dirs"].get(self._key(config_dir), {}).get("target_dirs", {})
            target_dirs.pop(self._key(target_dir), None)

    def record_owned_in(self, directory: Path, names: list[str]) -> None:
        """Replace the record of what we own in a directory, dropping the records of directories that are gone."""
        with self._changing() as state:
            owned = {key: entries for key, entries in state["owned"].items() if Path(key).is_dir()}
            if names:
                owned[self._key(directory)] = sorted(set(names))
            else:
                owned.pop(self._key(directory), None)
            state["owned"] = owned

    def forget(self) -> None:
        """Delete everything loom knows."""
        self.path.unlink(missing_ok=True)
        self._lock_file.unlink(missing_ok=True)

    def bases_of(self, key: str) -> list[str]:
        """The keys of the sources the one filed under key builds on."""
        return list(self._read()["sources"].get(key, {}).get("builds_on", []))

    def checkout_of(self, key: str) -> Path | None:
        """Where the source filed under key sits — None when it was never added."""
        known = self._read()["sources"].get(key)
        if known is None:
            return None
        return Path(known["path"])

    def source_of(self, key: str) -> str:
        """The source filed under key, as it was declared."""
        return self._read()["sources"].get(key, {}).get("source", key)

    def config_dirs(self) -> list[Path]:
        return [Path(config_dir) for config_dir in self._read()["config_dirs"]]

    def get_agent_name(self, config_dir: Path) -> str:
        """The name of the agent a recorded config dir belongs to."""
        return self._read()["config_dirs"][self._key(config_dir)]["agent"]

    def sources_pinned_to(self, config_dir: Path) -> list[str]:
        """The keys of the sources pinned to a config dir, in the order they were pinned."""
        return list(self._read()["config_dirs"].get(self._key(config_dir), {}).get("pinned", []))

    def target_dirs_in(self, config_dir: Path) -> list[Path]:
        return [Path(target_dir) for target_dir in self._target_dirs_of(config_dir)]

    def sources_declared_in(self, config_dir: Path) -> list[str]:
        """The keys of the sources this config dir's target dirs declare, each once."""
        declared = [key for keys in self._target_dirs_of(config_dir).values() for key in keys]
        return list(dict.fromkeys(declared))

    def config_dirs_of(self, target_dir: Path) -> list[Path]:
        """The config dirs a target dir is wired from — one per agent, unless it was wired from two."""
        key = self._key(target_dir)
        return [
            Path(config_dir)
            for config_dir, recorded in self._read()["config_dirs"].items()
            if key in recorded["target_dirs"]
        ]

    def owned_in(self, directory: Path) -> list[str]:
        """The names of the entries we own in a directory — the record for what cannot say so itself."""
        return self._read()["owned"].get(self._key(directory), [])

    @property
    def source_keys(self) -> list[str]:
        return list(self._read()["sources"])

    @property
    def target_dirs(self) -> list[Path]:
        """Every target dir wired from any config dir, each once."""
        wired = [
            target_dir for recorded in self._read()["config_dirs"].values() for target_dir in recorded["target_dirs"]
        ]
        return [Path(target_dir) for target_dir in dict.fromkeys(wired)]

    @contextmanager
    def _changing(self) -> Iterator[dict]:
        """Read, change and write under one lock: two sessions starting at once would otherwise lose a write."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # a lock file of its own, since the replace below swaps the registry for a new file
        self._lock_file.touch()
        with paths.locked(self._lock_file):
            state = self._read()
            was = json.dumps(state, sort_keys=True)
            yield state
            if json.dumps(state, sort_keys=True) != was:
                # written whole beside it, then swapped in, so a reader without the lock never sees half a file
                unfinished = self.path.with_name(f"{self.path.name}.unfinished")
                unfinished.write_text(json.dumps(state, indent=2) + "\n")
                unfinished.replace(self.path)

    def _read(self) -> dict:
        """Our state, with every key present — a file of another shape reads as empty, not broken."""
        state: dict = {"sources": {}, "config_dirs": {}, "owned": {}}
        if not self.path.is_file():
            return state
        on_disk = json.loads(self.path.read_text())
        return state | {key: on_disk[key] for key in state if isinstance(on_disk.get(key), type(state[key]))}

    def _target_dirs_of(self, config_dir: Path) -> dict[str, list[str]]:
        return self._read()["config_dirs"].get(self._key(config_dir), {}).get("target_dirs", {})

    @staticmethod
    def _key(directory: Path) -> str:
        """One key for a directory however its path is written."""
        return str(directory.expanduser().resolve())

    @property
    def _lock_file(self) -> Path:
        return self.path.with_name(f"{self.path.name}.lock")
