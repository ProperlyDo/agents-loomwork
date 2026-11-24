from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from loomwork import paths
from loomwork.sources.manifest import Manifest
from loomwork.sources.skill import Skill

if TYPE_CHECKING:
    from pathlib import Path

    from loomwork.targets.declaration import Declaration


@dataclass(frozen=True)
class Catalog:
    """What a set of sources defines, merged in order — a later source wins a name two of them define."""

    # where a source keeps each kind
    RULES_DIR_NAME: ClassVar[str] = "rules"
    SKILLS_DIR_NAME: ClassVar[str] = "skills"

    # rule name → its file
    rules: dict[str, Path]
    # skill name → its folder
    skills: dict[str, Path]
    # the names a source's loom.toml hands every target dir, among those defined
    global_rules: tuple[str, ...]
    global_skills: tuple[str, ...]
    # the universal layer, from the last source that carries one
    agents_md: Path | None

    @classmethod
    def of(cls, *checkouts: Path) -> Catalog:
        """The sources merged in order, a later one winning a name two of them define."""
        merged = cls(rules={}, skills={}, global_rules=(), global_skills=(), agents_md=None)
        for checkout in checkouts:
            merged = merged._overlaid_with(cls._shipped_by(checkout))
        return merged

    @classmethod
    def has_rules_or_skills(cls, checkout: Path) -> bool:
        """What makes a directory a source: rules, skills, or both. A universal AGENTS.md beside them is optional."""
        return (checkout / cls.RULES_DIR_NAME).is_dir() or (checkout / cls.SKILLS_DIR_NAME).is_dir()

    def rule_files(self, names: tuple[str, ...]) -> dict[str, Path]:
        """The files of the named rules, leaving out names no source defines."""
        return {name: self.rules[name] for name in names if name in self.rules}

    def skill_folders(self, names: tuple[str, ...]) -> dict[str, Path]:
        """The folders of the named skills, leaving out names no source defines."""
        return {name: self.skills[name] for name in names if name in self.skills}

    def undefined(self, declaration: Declaration) -> list[str]:
        """What the declaration names that no source defines, as "rule 'x'" or "skill 'y'"."""
        kinds = (("rule", declaration.rules, self.rules), ("skill", declaration.skills, self.skills))
        return [f"{kind} '{name}'" for kind, names, defined in kinds for name in names if name not in defined]

    @classmethod
    def _shipped_by(cls, checkout: Path) -> Catalog:
        """What one source ships: its rules and skills, and the ones its loom.toml hands every target dir."""
        rules = {rule.stem: rule for rule in (checkout / cls.RULES_DIR_NAME).glob("*.md")}
        skill_files = (checkout / cls.SKILLS_DIR_NAME).glob(f"*/{Skill.FILE_NAME}")
        skills = {skill_file.parent.name: skill_file.parent for skill_file in skill_files}
        manifest = Manifest.read(checkout)
        agents_md = None
        # a repo without a loom.toml keeps its AGENTS.md for its own contributors
        if (checkout / Manifest.FILE_NAME).is_file() and (checkout / paths.AGENTS_MD_NAME).is_file():
            agents_md = checkout / paths.AGENTS_MD_NAME
        return cls(
            rules=rules,
            skills=skills,
            # a source hands out only what it ships, never a name another source defines
            global_rules=tuple(name for name in manifest.global_rules if name in rules),
            global_skills=tuple(name for name in manifest.global_skills if name in skills),
            agents_md=agents_md,
        )

    def _overlaid_with(self, later: Catalog) -> Catalog:
        """This catalog with a later source laid over it, which wins a name both define."""
        rules = dict(sorted((self.rules | later.rules).items()))
        skills = dict(sorted((self.skills | later.skills).items()))
        handed_out_rules = {*self.global_rules, *later.global_rules}
        handed_out_skills = {*self.global_skills, *later.global_skills}
        agents_md = later.agents_md
        if agents_md is None:
            agents_md = self.agents_md
        return Catalog(
            rules=rules,
            skills=skills,
            global_rules=tuple(name for name in rules if name in handed_out_rules),
            global_skills=tuple(name for name in skills if name in handed_out_skills),
            agents_md=agents_md,
        )

    @property
    def offered_rules(self) -> tuple[str, ...]:
        """The rules a target dir chooses from: every one not handed out anyway."""
        return tuple(name for name in self.rules if name not in self.global_rules)

    @property
    def offered_skills(self) -> tuple[str, ...]:
        return tuple(name for name in self.skills if name not in self.global_skills)
