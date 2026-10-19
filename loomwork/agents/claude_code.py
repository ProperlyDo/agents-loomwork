from __future__ import annotations

import json
import shlex
import shutil
import sys
from pathlib import Path
from typing import ClassVar

from loomwork import COMMAND_NAME, paths
from loomwork.agents.base import Agent
from loomwork.declaration import Declaration
from loomwork.installation import Installation


class ClaudeCode(Agent):
    """Mechanical loader and the host: its engine loads whatever files exist, so projects get wired — and its SessionStart hook is what runs sync for every agent."""

    NAME = "claude"

    COMMAND = "claude"
    # at user level Claude reads CLAUDE.md only
    AGENTS_MD_NAME = "CLAUDE.md"
    # where Claude keeps its config unless it is launched with CONFIG_DIR_ENV
    DEFAULT_CONFIG_DIR: ClassVar[Path] = Path("~/.claude").expanduser()
    CONFIG_DIR_ENV: ClassVar[str] = "CLAUDE_CONFIG_DIR"
    # read recursively, so our rules sit one level down beside the project's own
    PROJECT_RULES_DIR = ".claude/rules"
    PROJECT_SKILLS_DIR = ".claude/skills"
    # a session waits on its start hooks, so ours has to be quick or get out of the way
    HOOK_TIMEOUT_SECONDS: ClassVar[int] = 10

    def __init__(self, config_dir: Path) -> None:
        self._config_dir = config_dir

    @property
    def config_dir(self) -> Path:
        return self._config_dir

    def bridge(self, installation: Installation) -> tuple[Path, ...]:
        """Claude's user-level surfaces, and the session hook that keeps every project in sync."""
        return super().bridge(installation) + self._register_hook(installation)

    def unbridge(self, installation: Installation) -> None:
        """Mirror of bridge(), the session hook included."""
        self._strip_hook(installation, self.config_dir / "settings.json")
        super().unbridge(installation)

    def our_hook(self, installation: Installation, hook: dict) -> bool:
        """Ours by the command it calls, whatever path or entry-point name it was written with."""
        # the hook line guards before it calls, so what it actually runs is the last statement
        words = shlex.split(hook.get("command", "").rsplit(";", 1)[-1])
        return bool(words) and Path(words[0]).name == COMMAND_NAME and "sync" in words[1:]

    def _register_hook(self, installation: Installation) -> tuple[Path, ...]:
        """Put our SessionStart hook in this config dir's settings, keeping every hook that is already there."""
        settings_file = self.config_dir / "settings.json"
        settings = json.loads(settings_file.read_text()) if settings_file.is_file() else {}
        was = json.dumps(settings, sort_keys=True)
        entries = settings.setdefault("hooks", {}).setdefault("SessionStart", [])
        # replace-not-append: our own entries go first, so reruns and a moved install converge on one line
        self._drop_our_entries(installation, entries)
        hook = {"type": "command", "command": self._hook_command(installation), "timeout": self.HOOK_TIMEOUT_SECONDS}
        entries.append({"hooks": [hook]})
        if json.dumps(settings, sort_keys=True) != was:
            settings_file.parent.mkdir(parents=True, exist_ok=True)
            settings_file.write_text(json.dumps(settings, indent=2) + "\n")
        return (settings_file,)

    def _strip_hook(self, installation: Installation, settings_file: Path) -> None:
        """Remove exactly our entries from a settings file, and any key or file that empties out."""
        if not settings_file.is_file():
            return
        settings = json.loads(settings_file.read_text())
        entries = settings.get("hooks", {}).get("SessionStart")
        if entries is None:
            return
        self._drop_our_entries(installation, entries)
        if not entries:
            del settings["hooks"]["SessionStart"]
        if not settings["hooks"]:
            del settings["hooks"]
        if not settings:
            # an empty settings file is litter, and Claude reads its absence the same way
            settings_file.unlink()
            paths.remove_if_empty(settings_file.parent)
            return
        settings_file.write_text(json.dumps(settings, indent=2) + "\n")

    def _drop_our_entries(self, installation: Installation, entries: list[dict]) -> None:
        for entry in entries:
            entry["hooks"] = [hook for hook in entry.get("hooks", []) if not self.our_hook(installation, hook)]
        entries[:] = [entry for entry in entries if entry.get("hooks")]

    def _hook_command(self, installation: Installation) -> str:
        """The guard is the opt-in: a project with no declaration never calls us, and the hook still exits clean."""
        # the profile is named, so a session syncs the config dir it was launched with
        return (
            f'[ -f "$CLAUDE_PROJECT_DIR/{Declaration.FILE_NAME}" ] || exit 0; '
            f"{self._loom_command()} --config-dir {shlex.quote(str(self.config_dir))} "
            f'sync --for {self.NAME} "$CLAUDE_PROJECT_DIR"'
        )

    def _loom_command(self) -> str:
        """How the hook calls us: by the full path we were started from, since its shell may not have us on PATH."""
        found = shutil.which(sys.argv[0])
        # started as anything but our own command (a test runner, python -m), the bare name is all we know
        if not found or Path(found).name != COMMAND_NAME:
            return COMMAND_NAME
        return shlex.quote(str(Path(found).absolute()))
