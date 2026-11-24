from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from loomwork import toml_file

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class DeclaredSource:
    """One [[source]] block of a declaration: where the rules repo is, and what the target dir takes from it."""

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

    def toml_lines(self) -> list[str]:
        """The block's TOML lines, leaving out an empty rules or skills list."""
        lines = [f'source = "{self.source}"']
        for key, names in (("rules", self.rules), ("skills", self.skills)):
            if names:
                quoted = ", ".join(f'"{name}"' for name in names)
                lines.append(f"{key} = [{quoted}]")
        return lines


@dataclass(frozen=True)
class Declaration:
    """A target dir's .agents.toml: the sources it uses and what it takes from each. Its presence is the opt-in."""

    FILE_NAME: ClassVar[str] = ".agents.toml"
    TABLE: ClassVar[str] = "source"

    sources: tuple[DeclaredSource, ...]

    @classmethod
    def read(cls, target_dir: Path) -> Declaration | None:
        """The target dir's declaration, or None when it carries none — which reads as the opt-out."""
        declaration_file = target_dir / cls.FILE_NAME
        if not declaration_file.is_file():
            return None
        declared = toml_file.parsed(declaration_file)
        listed = declared.get(cls.TABLE)
        if isinstance(listed, list):
            sources = tuple(DeclaredSource.of(entry) for entry in listed if entry.get("source"))
            if not sources:
                return None
            return cls(sources)
        if not declared.get("source"):
            return None
        return cls((DeclaredSource.of(declared),))

    def write(self, target_dir: Path) -> Path:
        declaration_file = target_dir / self.FILE_NAME
        declaration_file.write_text("\n".join(self._lines()) + "\n")
        return declaration_file

    def _lines(self) -> list[str]:
        lines = []
        for declared in self.sources:
            lines += [f"[[{self.TABLE}]]", *declared.toml_lines(), ""]
        return lines[:-1]

    @property
    def rules(self) -> tuple[str, ...]:
        """Every rule this target dir asks for, in the order its sources were declared."""
        return tuple(name for declared in self.sources for name in declared.rules)

    @property
    def skills(self) -> tuple[str, ...]:
        return tuple(name for declared in self.sources for name in declared.skills)
