from __future__ import annotations

import json
import shlex
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from loomwork import COMMAND_NAME, paths
from loomwork.agents.base import Agent
from loomwork.targets.declaration import Declaration

if TYPE_CHECKING:
    from loomwork.installation import Installation


class ClaudeCode(Agent):
    """The host: its SessionStart hook is what runs sync for every agent."""

    NAME = "claude"

    COMMAND = "claude"
    # at user level Claude reads CLAUDE.md only
    AGENTS_MD_NAME = "CLAUDE.md"
    CONFIG_DIR_ENV = "CLAUDE_CONFIG_DIR"
    # read recursively, so our rules sit one level down beside the target dir's own
    TARGET_RULES_DIR = ".claude/rules"
    TARGET_SKILLS_DIR = ".claude/skills"
    # a session waits on its start hooks, so ours has to be quick or get out of the way
    HOOK_TIMEOUT_SECONDS: ClassVar[int] = 10
    # the settings key Claude runs a hook under when a session opens
    HOOK_EVENT: ClassVar[str] = "SessionStart"

    def lay_global_files(self, installation: Installation) -> tuple[Path, ...]:
        """Claude's user-level surfaces, and the session hook that keeps every target dir in sync."""
        return super().lay_global_files(installation) + self._register_hook()

    def clear_global_files(self, installation: Installation) -> None:
        """Mirror of lay_global_files(), the session hook included."""
        self._strip_hook()
        super().clear_global_files(installation)

    def _register_hook(self) -> tuple[Path, ...]:
        """Put our SessionStart hook in this config dir's settings, keeping every hook that is already there."""
        settings_file = self._settings_file
        settings: dict = {}
        if settings_file.is_file():
            settings = json.loads(settings_file.read_text())
        was = json.dumps(settings, sort_keys=True)
        entries = settings.setdefault("hooks", {}).setdefault(self.HOOK_EVENT, [])
        # our old entries go before the new one is appended, so reruns and a moved install converge on one
        self._drop_our_entries(entries)
        hook = {"type": "command", "command": self._hook_command(), "timeout": self.HOOK_TIMEOUT_SECONDS}
        entries.append({"hooks": [hook]})
        if json.dumps(settings, sort_keys=True) != was:
            settings_file.parent.mkdir(parents=True, exist_ok=True)
            settings_file.write_text(json.dumps(settings, indent=2) + "\n")
        return (settings_file,)

    def _strip_hook(self) -> None:
        """Remove exactly our entries from the settings file, and any key or file that empties out."""
        settings_file = self._settings_file
        if not settings_file.is_file():
            return
        settings = json.loads(settings_file.read_text())
        entries = settings.get("hooks", {}).get(self.HOOK_EVENT)
        if entries is None:
            return
        self._drop_our_entries(entries)
        if not entries:
            del settings["hooks"][self.HOOK_EVENT]
        if not settings["hooks"]:
            del settings["hooks"]
        if not settings:
            # Claude reads a missing settings file as an empty one
            settings_file.unlink()
            paths.remove_if_empty(settings_file.parent)
            return
        settings_file.write_text(json.dumps(settings, indent=2) + "\n")

    def _drop_our_entries(self, entries: list[dict]) -> None:
        for entry in entries:
            entry["hooks"] = [hook for hook in entry.get("hooks", []) if not self._is_our_hook(hook)]
        entries[:] = [entry for entry in entries if entry.get("hooks")]

    def _hook_command(self) -> str:
        """The hook line: a guard on the declaration, then our sync."""
        return (
            # the guard is the opt-in: a target dir with no declaration never calls us
            f'[ -f "$CLAUDE_PROJECT_DIR/{Declaration.FILE_NAME}" ] || exit 0; '
            # the dir is named, so a sync knows which of the agent's dirs the asking session reads
            f"{self._loom_command()} {self.config_dir_option()} {shlex.quote(str(self.config_dir))} "
            f'sync --for {self.NAME} "$CLAUDE_PROJECT_DIR"'
        )

    @staticmethod
    def _is_our_hook(hook: dict) -> bool:
        """Ours by the command it calls, whatever path or entry-point name it was written with."""
        # the hook line guards before it calls, so what it actually runs is the last statement
        words = shlex.split(hook.get("command", "").rsplit(";", 1)[-1])
        return bool(words) and Path(words[0]).name == COMMAND_NAME and "sync" in words[1:]

    @staticmethod
    def _loom_command() -> str:
        """How the hook calls us: by the full path we were started from, since its shell may not have us on PATH."""
        found = shutil.which(sys.argv[0])
        # started as anything but our own command (a test runner, python -m), the bare name is all we know
        if not found or Path(found).name != COMMAND_NAME:
            return COMMAND_NAME
        return shlex.quote(str(Path(found).absolute()))

    @classmethod
    def standard_config_dir(cls) -> Path:
        return Path("~/.claude").expanduser()

    @property
    def _settings_file(self) -> Path:
        return self.config_dir / "settings.json"
