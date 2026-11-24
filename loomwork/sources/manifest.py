from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from loomwork import toml_file
from loomwork.targets.declaration import Declaration

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class Manifest:
    """A source's loom.toml: the sources it builds on, and the rules and skills it hands every target dir."""

    FILE_NAME: ClassVar[str] = "loom.toml"
    TABLE: ClassVar[str] = "global"

    # the same [[source]] blocks a target dir writes, meaning "I build on this" rather than "I take this"
    builds_on: tuple[str, ...] = ()
    global_rules: tuple[str, ...] = ()
    global_skills: tuple[str, ...] = ()

    @classmethod
    def read(cls, source: Path) -> Manifest:
        """The source's manifest — an empty one when it has no loom.toml."""
        manifest_file = source / cls.FILE_NAME
        if not manifest_file.is_file():
            return cls()
        document = toml_file.parsed(manifest_file)
        marked_global = document.get(cls.TABLE, {})
        blocks = document.get(Declaration.TABLE)
        if not isinstance(blocks, list):
            blocks = []
        return cls(
            builds_on=tuple(entry["source"] for entry in blocks if entry.get("source")),
            global_rules=tuple(marked_global.get("rules", ())),
            global_skills=tuple(marked_global.get("skills", ())),
        )
