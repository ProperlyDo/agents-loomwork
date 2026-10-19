from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from loomwork.output import error


@dataclass(frozen=True)
class DeclaredSource:
    """One [[source]] block of a declaration: where the rules repo is, and what the project takes from it."""

    source: str
    rules: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()

    @classmethod
    def of(cls, declared: dict) -> DeclaredSource:
        return cls(
            source=declared["source"],
            rules=tuple(declared.get("rules", ())),
            skills=tuple(declared.get("skills", ())),
        )

    def spelled(self) -> list[str]:
        """The block's TOML lines, leaving out an empty rules or skills list."""
        lines = [f'source = "{self.source}"']
        for key, names in (("rules", self.rules), ("skills", self.skills)):
            if names:
                quoted = ", ".join(f'"{name}"' for name in names)
                lines.append(f"{key} = [{quoted}]")
        return lines


@dataclass(frozen=True)
class Declaration:
    """A project's .agents.toml: the sources it uses and what it takes from each. Its presence is the opt-in."""

    FILE_NAME: ClassVar[str] = ".agents.toml"
    TABLE: ClassVar[str] = "source"

    sources: tuple[DeclaredSource, ...]

    @classmethod
    def read(cls, project_dir: Path) -> Declaration | None:
        """The project's declaration, or None when it carries none — which reads as the opt-out."""
        declaration_file = project_dir / cls.FILE_NAME
        if not declaration_file.is_file():
            return None
        declared = _parsed(declaration_file)
        listed = declared.get(cls.TABLE)
        if isinstance(listed, list):
            sources = tuple(DeclaredSource.of(entry) for entry in listed if entry.get("source"))
            if not sources:
                return None
            return cls(sources)
        if not declared.get("source"):
            return None
        return cls((DeclaredSource.of(declared),))

    def write(self, project_dir: Path) -> Path:
        """Write the file into the project, returning its path."""
        declaration_file = project_dir / self.FILE_NAME
        declaration_file.write_text("\n".join(self._lines()) + "\n")
        return declaration_file

    @property
    def rules(self) -> tuple[str, ...]:
        """Every rule this project asks for, in the order its sources were declared."""
        return tuple(name for declared in self.sources for name in declared.rules)

    @property
    def skills(self) -> tuple[str, ...]:
        return tuple(name for declared in self.sources for name in declared.skills)

    def _lines(self) -> list[str]:
        lines = []
        for declared in self.sources:
            lines += [f"[[{self.TABLE}]]", *declared.spelled(), ""]
        return lines[:-1]


@dataclass(frozen=True)
class Manifest:
    """A source's loom.toml: the sources it builds on, and the rules and skills it hands every project."""

    FILE_NAME: ClassVar[str] = "loom.toml"
    TABLE: ClassVar[str] = "global"

    # the same [[source]] blocks a project writes, meaning "I build on this" rather than "I take this"
    builds_on: tuple[str, ...] = ()
    global_rules: tuple[str, ...] = ()
    global_skills: tuple[str, ...] = ()

    @classmethod
    def read(cls, source: Path) -> Manifest:
        """The source's manifest — an empty one when it has no loom.toml."""
        manifest_file = source / cls.FILE_NAME
        if not manifest_file.is_file():
            return cls()
        document = _parsed(manifest_file)
        marked_global = document.get(cls.TABLE, {})
        blocks = document.get(Declaration.TABLE)
        if not isinstance(blocks, list):
            blocks = []
        return cls(
            builds_on=tuple(entry["source"] for entry in blocks if entry.get("source")),
            global_rules=tuple(marked_global.get("rules", ())),
            global_skills=tuple(marked_global.get("skills", ())),
        )


def _parsed(toml_file: Path) -> dict:
    """The file's contents, or a one-line failure naming it — a session hook's error shows its first line only."""
    try:
        return tomllib.loads(toml_file.read_text())
    except tomllib.TOMLDecodeError as broken:
        error(f"{toml_file}: {broken}")
