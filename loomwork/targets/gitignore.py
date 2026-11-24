from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from loomwork import COMMAND_NAME, paths
from loomwork.output import info
from loomwork.targets.declaration import Declaration

if TYPE_CHECKING:
    from pathlib import Path

    from loomwork.agents import Agent


class Gitignore:
    """A target dir's .gitignore, as far as the files loom writes into the target dir go."""

    FILE_NAME: ClassVar[str] = ".gitignore"

    def __init__(self, target_dir: Path, agents: tuple[Agent, ...]) -> None:
        self.target_dir = target_dir
        # every agent whose folders loom may write into the target dir
        self.agents = agents

    def add_ours(self) -> None:
        """Append what loom writes into the target dir and the file does not cover yet."""
        unignored = self.unignored()
        if not unignored:
            return
        block = f"# written per machine by {COMMAND_NAME}, from {Declaration.FILE_NAME}\n" + "\n".join(unignored) + "\n"
        existing = self._text()
        if existing:
            block = existing.rstrip("\n") + "\n\n" + block
        (self.target_dir / self.FILE_NAME).write_text(block)
        info(f"ignored {', '.join(unignored)} in {self.FILE_NAME}")

    def unignored(self) -> list[str]:
        """What loom writes into the target dir that its .gitignore does not cover yet."""
        # whole lines, since .claude/settings.local.json contains .claude/ yet leaves the rest of it unignored
        ignored = {line.strip().strip("/") for line in self._text().splitlines()}
        return [path for path in self._ours if path.strip("/") not in ignored]

    def _text(self) -> str:
        ignore_file = self.target_dir / self.FILE_NAME
        if not ignore_file.is_file():
            return ""
        return ignore_file.read_text()

    @property
    def _ours(self) -> tuple[str, ...]:
        """What loom writes into a target dir, as .gitignore lines: its .agents/, and every agent's own folders."""
        folders = {folder for agent in self.agents for folder in agent.target_folders()}
        return (f"{paths.AGENTS_DIR_NAME}/", *(f"{folder}/" for folder in sorted(folders)))
