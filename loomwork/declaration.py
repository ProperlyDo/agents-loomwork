from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar


@dataclass(frozen=True)
class Declaration:
    """What a project commits about the rules it wants — the opt-in, and the only file of ours it tracks."""

    source: str
    namespace: str
    rules: tuple[str, ...]

    # TOML, not YAML: tomllib ships with Python, so the file gets a real parser and we keep no dependencies
    FILE_NAME: ClassVar[str] = ".agents.toml"

    @classmethod
    def read(cls, project_dir: Path) -> Declaration | None:
        """The project's declaration, or None when it carries none — which reads as the opt-out."""
        declaration_file = project_dir / cls.FILE_NAME
        if not declaration_file.is_file():
            return None
        declared = tomllib.loads(declaration_file.read_text())
        source = declared.get("source")
        if not source:
            return None
        return cls(
            source=source,
            namespace=declared.get("namespace") or cls.namespace_of(source),
            rules=tuple(declared.get("rules", ())),
        )

    @staticmethod
    def segments(source: str) -> tuple[str, str, str]:
        """`<host>/<owner>/<repo>` split out, so a declared source can become a clone url."""
        parts = [part for part in source.rstrip("/").removesuffix(".git").split("/") if part]
        if len(parts) < len(("host", "owner", "repo")):
            raise SystemExit(f"'{source}' is no <host>/<owner>/<repo> — cannot tell where to clone it from")
        return parts[-3], parts[-2], parts[-1]

    @classmethod
    def namespace_of(cls, source: str) -> str:
        """The owner segment of `<domain>/<owner>/<repo>`, lowercased — spell `namespace` out when that reads badly."""
        try:
            return cls.segments(source)[1].lower()
        except SystemExit:
            return source.lower()
