from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import ClassVar

import yaml


@dataclass(frozen=True)
class Skill:
    """A skill folder and what its SKILL.md declares."""

    FILE_NAME: ClassVar[str] = "SKILL.md"
    FRONTMATTER_FENCE: ClassVar[str] = "---"

    folder: Path

    @property
    def name(self) -> str:
        return self.folder.name

    @property
    def description(self) -> str:
        return str(self.frontmatter.get("description") or "").strip()

    @property
    def is_manual(self) -> bool:
        """True when the frontmatter sets `disable-model-invocation`: only the user may start the skill."""
        return self.frontmatter.get("disable-model-invocation") is True

    @cached_property
    def frontmatter(self) -> dict:
        """SKILL.md's frontmatter as a dict — empty when it is missing or invalid."""
        try:
            opening, fenced, block = (self.folder / self.FILE_NAME).read_text().partition(self.FRONTMATTER_FENCE)
        except OSError:
            return {}
        if opening.strip() or not fenced:
            return {}
        try:
            read = yaml.safe_load(block.partition(f"\n{self.FRONTMATTER_FENCE}")[0])
        except yaml.YAMLError:
            return {}
        if not isinstance(read, dict):
            return {}
        return read
