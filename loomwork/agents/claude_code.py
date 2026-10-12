from __future__ import annotations

import json
import os
from pathlib import Path
from typing import ClassVar

from loomwork import COMMAND_NAME, TOOL_NAME
from loomwork.agents.base import EnvConfiguredAgent
from loomwork.installation import Installation, rmdir_quiet


class ClaudeCode(EnvConfiguredAgent):
    """Mechanical loader and the host: its engine loads whatever files exist, so projects get wired — and its SessionStart hook is what runs sync for every agent."""

    NAME = "claude"

    CONFIG_DIR_ENV = "CLAUDE_CONFIG_DIR"
    DEFAULT_CONFIG_DIR = "~/.claude"
    # the package name is here for hooks written before the console script became `loom` — recognised for removal, never written
    OUR_COMMAND_NAMES: ClassVar[frozenset[str]] = frozenset({COMMAND_NAME, TOOL_NAME})
    # Claude reads CLAUDE.md and never AGENTS.md, so the project's own instructions need an importer
    # .claude/rules points at the shared container one level up, so the link resolves inside the project
    PROJECT_RULES_TARGET: ClassVar[str] = "../.agents/rules"
    PROJECT_SHAPES: ClassVar[frozenset[str]] = frozenset({PROJECT_RULES_TARGET})
    # set only while Claude runs a plugin's hook, and it points at the plugin copy — which ships the rules
    PLUGIN_ROOT_ENV: ClassVar[str] = "CLAUDE_PLUGIN_ROOT"
    # written by versions before Claude read a project's AGENTS.md natively — recognised for removal, never written
    ENTRY_FILE: ClassVar[str] = "CLAUDE.local.md"

    @classmethod
    def offered_source(cls) -> Path | None:
        root = os.environ.get(cls.PLUGIN_ROOT_ENV)
        return Path(root).resolve() if root else None

    @staticmethod
    def names_source(source: Path) -> str | None:
        """A plugin names itself in its manifest, which is namespace enough for a machine that never ran `init`."""
        manifest = source / ".claude-plugin" / "plugin.json"
        if not manifest.is_file():
            return None
        return json.loads(manifest.read_text()).get("name")

    def bridge(self, installation: Installation) -> None:
        """Claude's two bridge surfaces — CLAUDE.md and rules — laid in one pass; skills are the skills CLI's."""
        self.bridge_claude_md(installation)
        self.bridge_rules(installation)

    def bridge_claude_md(self, installation: Installation) -> None:
        """Claude's user-level CLAUDE.md becomes our AGENTS.md — the universal layer in every session."""
        installation.copy_rule(installation.agents_file, self.config_dir / "CLAUDE.md")

    def bridge_rules(self, installation: Installation) -> None:
        """Only the stack-neutral rules bridge globally — stack rules stay per-project, where "html" is unambiguous."""
        bridge_dir = self.rules_bridge_dir(installation)
        # an owned link here is a leftover wholesale shape — it must yield to the real dir
        if installation.owned(bridge_dir):
            bridge_dir.unlink()
        neutral_rules = [
            rule for rule in sorted(installation.rules_dir.glob("*.md")) if installation.is_stack_neutral(rule)
        ]
        installation.reconcile(installation.by_name(neutral_rules), bridge_dir)
        installation.prune(self.config_dir / "rules", {installation.namespace})

    def unbridge(self, installation: Installation) -> None:
        """Remove both bridge surfaces."""
        bridge_dir = self.rules_bridge_dir(installation)
        installation.prune(bridge_dir, set())
        rmdir_quiet(bridge_dir)
        installation.prune(self.config_dir / "rules", set())
        claude_file = self.config_dir / "CLAUDE.md"
        if installation.owned(claude_file):
            claude_file.unlink()

    def bridge_project(self, installation: Installation, project_dir: Path) -> None:
        """Link .claude/rules at the project's .agents/rules wholesale."""
        rules_link = project_dir / ".claude" / "rules"
        # a leftover real rules dir blocks the wholesale link — clear it when it holds nothing foreign
        if rules_link.is_dir() and not rules_link.is_symlink():
            installation.prune(rules_link, set())
            rmdir_quiet(rules_link)
        (project_dir / ".claude").mkdir(exist_ok=True)
        installation.symlink(self.PROJECT_RULES_TARGET, rules_link)
        self.drop_entry_file(installation, project_dir)
        # the plugin's own SessionStart hook covers every project, so clear the per-project one earlier versions wrote
        self.strip_hook(installation, self.local_settings_file(project_dir))

    def drop_entry_file(self, installation: Installation, project_dir: Path) -> None:
        """Claude reads the project's AGENTS.md itself, and our importer would suppress exactly that."""
        entry_file = project_dir / self.ENTRY_FILE
        if installation.owned(entry_file):
            entry_file.unlink()

    def unbridge_project(self, installation: Installation, project_dir: Path) -> None:
        """Drop the hook and the wholesale rules link, the link only when no config's container remains behind it."""
        self.strip_hook(installation, self.local_settings_file(project_dir))
        self.drop_entry_file(installation, project_dir)
        rules_link = project_dir / ".claude" / "rules"
        if not (project_dir / ".agents" / "rules").exists() and installation.owned(rules_link):
            rules_link.unlink()

    def strip_hook(self, installation: Installation, settings_file: Path) -> None:
        """Remove exactly our entries from a settings file and any containers that empty out."""
        if not settings_file.is_file():
            return
        settings = json.loads(settings_file.read_text())
        entries = settings.get("hooks", {}).get("SessionStart")
        if entries is None:
            return
        self.drop_our_entries(installation, entries)
        if not entries:
            del settings["hooks"]["SessionStart"]
        if not settings["hooks"]:
            del settings["hooks"]
        if not settings:
            # an empty settings file is litter, and Claude reads its absence the same way
            settings_file.unlink()
            rmdir_quiet(settings_file.parent)
            return
        settings_file.write_text(json.dumps(settings, indent=2) + "\n")

    def drop_our_entries(self, installation: Installation, entries: list[dict]) -> None:
        for entry in entries:
            entry["hooks"] = [hook for hook in entry.get("hooks", []) if not self.our_hook(installation, hook)]
        entries[:] = [entry for entry in entries if entry.get("hooks")]

    def our_hook(self, installation: Installation, hook: dict) -> bool:
        """Ours by the command it calls, whatever path or entry-point name it was written with."""
        command = hook.get("command", "")
        called, _, rest = command.partition(" ")
        if Path(called).name in self.OUR_COMMAND_NAMES and rest.startswith("sync"):
            return True
        return "/install.py sync" in command and f"--namespace {installation.namespace}" in command

    def local_settings_file(self, project_dir: Path) -> Path:
        return project_dir / ".claude" / "settings.local.json"

    def rules_bridge_dir(self, installation: Installation) -> Path:
        return self.config_dir / "rules" / installation.namespace

    def forget_machine_hook(self, installation: Installation) -> None:
        """Nothing writes hooks any more; this clears what versions before the plugin left in settings.json."""
        self.strip_hook(installation, self.config_dir / "settings.json")
