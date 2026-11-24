from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, ClassVar

import yaml

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class Skill:
    """A skill folder and what its SKILL.md declares."""

    FILE_NAME: ClassVar[str] = "SKILL.md"
    FRONTMATTER_FENCE: ClassVar[str] = "---"

    folder: Path

    @property
    def is_manual(self) -> bool:
        """True when the frontmatter sets `disable-model-invocation`: only the user may start the skill."""
        return self._frontmatter.get("disable-model-invocation") is True

    @property
    def description(self) -> str:
        return str(self._frontmatter.get("description") or "").strip()

    @cached_property
    def _frontmatter(self) -> dict:
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

    @property
    def name(self) -> str:
        return self.folder.name
