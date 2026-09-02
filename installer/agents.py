from __future__ import annotations

import json
import os
import shlex
from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar

from installer.installation import Installation, rmdir_quiet


class Agent(ABC):
    """A supported tool: its config-dir contract, presence detection, bridges, and optional lifecycle registration."""

    # each agent names the env var it honors — never invent one the tool itself doesn't read
    CONFIG_DIR_ENV: ClassVar[str]
    DEFAULT_CONFIG_DIR: ClassVar[str]

    def present(self) -> bool:
        """An agent that never ran gets nothing — config dirs are never fabricated for absent tools."""
        return self.config_dir.is_dir()

    @abstractmethod
    def bridge(self, installation: Installation) -> None:
        """Lay this tool's links into its config dir, pointing at the installation's."""

    @abstractmethod
    def unbridge(self, installation: Installation) -> None:
        """Remove every link bridge() laid, touching nothing foreign."""

    def register(self, installation: Installation) -> None:
        """Hook registration is a no-op for agents that only consume links."""
        return None

    def unregister(self, installation: Installation) -> None:
        """Mirror of register() — a no-op unless the agent carries lifecycle state."""
        return None

    def bridge_project(self, installation: Installation, project_dir: Path) -> None:
        """A no-op unless the tool keeps per-project state to point at the container."""
        return None

    def unbridge_project(self, installation: Installation, project_dir: Path) -> None:
        """Mirror of bridge_project() — remove per-project pointers when the container is gone."""
        return None

    @property
    def config_dir(self) -> Path:
        """The tool's own config dir — its honored env var when set, else its default."""
        configured = os.environ.get(self.CONFIG_DIR_ENV)
        if configured:
            return Path(configured).expanduser()
        return self.default_config_dir()

    def default_config_dir(self) -> Path:
        """The override seam for computed defaults — OpenCode replaces this with its XDG fallback."""
        return Path(self.DEFAULT_CONFIG_DIR).expanduser()


class ClaudeCode(Agent):
    CONFIG_DIR_ENV = "CLAUDE_CONFIG_DIR"
    DEFAULT_CONFIG_DIR = "~/.claude"
    HOOK_TIMEOUT_SECONDS: ClassVar[int] = 10

    def bridge(self, installation: Installation) -> None:
        """Claude's three bridge surfaces — CLAUDE.md, rules, skills — laid in one pass."""
        self.bridge_claude_md(installation)
        self.bridge_rules(installation)
        self.bridge_skills(installation)

    def bridge_claude_md(self, installation: Installation) -> None:
        """Claude's user-level CLAUDE.md becomes our AGENTS.md — the universal layer in every session."""
        installation.symlink(installation.agents_file, self.config_dir / "CLAUDE.md")

    def bridge_rules(self, installation: Installation) -> None:
        """Only the stack-neutral rules bridge globally — stack rules stay per-project, where "html" is unambiguous."""
        bridge_dir = self.rules_bridge_dir(installation)
        # an owned link here is a leftover wholesale shape — it must yield to the real dir
        if installation.owned(bridge_dir):
            bridge_dir.unlink()
        neutral_rules = [rule for rule in sorted(installation.rules_dir.glob("*.md")) if installation.is_stack_neutral(rule)]
        installation.reconcile(neutral_rules, bridge_dir)
        installation.prune(self.config_dir / "rules", {installation.namespace})

    def bridge_skills(self, installation: Installation) -> None:
        """Per-skill links, so ours sit beside skills-CLI installs without owning the directory."""
        our_skills = [installation.skills_dir / skill_dir.name for skill_dir in installation.shipped_skill_dirs()]
        installation.reconcile(our_skills, self.config_dir / "skills")

    def unbridge(self, installation: Installation) -> None:
        """Remove all three bridge surfaces."""
        bridge_dir = self.rules_bridge_dir(installation)
        installation.prune(bridge_dir, set())
        rmdir_quiet(bridge_dir)
        installation.prune(self.config_dir / "rules", set())
        installation.prune(self.config_dir / "skills", set())
        claude_file = self.config_dir / "CLAUDE.md"
        if installation.owned(claude_file):
            claude_file.unlink()

    def bridge_project(self, installation: Installation, project_dir: Path) -> None:
        """Link .claude/rules at the project's .agents/rules wholesale, plus the skills link when it is missing."""
        rules_link = project_dir / ".claude" / "rules"
        # a leftover real rules dir blocks the wholesale link — clear it when it holds nothing foreign
        if rules_link.is_dir() and not rules_link.is_symlink():
            installation.prune(rules_link, set())
            rmdir_quiet(rules_link)
        (project_dir / ".claude").mkdir(exist_ok=True)
        installation.symlink(installation.PROJECT_RULES_TARGET, rules_link)
        # the skills link is the skills CLI's, but re-laying it after a wiped .claude is trivially derivable — create-only, never managed
        skills_link = project_dir / ".claude" / "skills"
        if (project_dir / ".agents" / "skills").is_dir() and not skills_link.exists() and not skills_link.is_symlink():
            skills_link.symlink_to("../.agents/skills")

    def unbridge_project(self, installation: Installation, project_dir: Path) -> None:
        """Drop the wholesale rules link, but only when no config's container remains behind it."""
        rules_link = project_dir / ".claude" / "rules"
        if not (project_dir / ".agents" / "rules").exists() and installation.owned(rules_link):
            rules_link.unlink()

    def hook_command(self, installation: Installation) -> str:
        """The SessionStart hook line — the only persisted home of namespace and config dir; the shell fills in the session's project."""
        return (
            f"{shlex.quote(f'{installation.repo_dir}/install.py')} sync"
            f" --namespace {installation.namespace} --config-dir {shlex.quote(str(installation.config_dir))}"
            ' "$CLAUDE_PROJECT_DIR"'
        )

    def register(self, installation: Installation) -> None:
        """Merge our SessionStart hook into settings.json, preserving every foreign hook."""
        settings = json.loads(self.settings_file.read_text()) if self.settings_file.is_file() else {}
        entries = settings.setdefault("hooks", {}).setdefault("SessionStart", [])
        # replace-not-append: every entry with our clone prefix goes first, so reruns and older hook lines converge on one entry
        for entry in entries:
            entry["hooks"] = self.foreign_hooks(installation, entry)
        entries[:] = [entry for entry in entries if entry.get("hooks")]
        entries.append({"hooks": [{"type": "command", "command": self.hook_command(installation), "timeout": self.HOOK_TIMEOUT_SECONDS}]})
        self.settings_file.write_text(json.dumps(settings, indent=2) + "\n")

    def unregister(self, installation: Installation) -> None:
        """Remove exactly our hook entries and any containers that emptied; foreign hooks stay."""
        if not self.settings_file.is_file():
            return
        settings = json.loads(self.settings_file.read_text())
        entries = settings.get("hooks", {}).get("SessionStart")
        if entries is None:
            return
        for entry in entries:
            entry["hooks"] = self.foreign_hooks(installation, entry)
        entries[:] = [entry for entry in entries if entry.get("hooks")]
        if not entries:
            del settings["hooks"]["SessionStart"]
        if not settings["hooks"]:
            del settings["hooks"]
        self.settings_file.write_text(json.dumps(settings, indent=2) + "\n")

    def foreign_hooks(self, installation: Installation, entry: dict) -> list[dict]:
        """Everything in the entry that this installation did not register."""
        return [hook for hook in entry.get("hooks", []) if not self.our_hook(installation, hook)]

    def our_hook(self, installation: Installation, hook: dict) -> bool:
        """From this clone — or a moved clone's stale line, matched by the sync signature carrying our namespace."""
        command = hook.get("command", "")
        if f"{installation.repo_dir}/" in command:
            return True
        return "/install.py sync" in command and f"--namespace {installation.namespace}" in command

    def rules_bridge_dir(self, installation: Installation) -> Path:
        return self.config_dir / "rules" / installation.namespace

    @property
    def settings_file(self) -> Path:
        return self.config_dir / "settings.json"


class OpenCode(Agent):
    CONFIG_DIR_ENV = "OPENCODE_CONFIG_DIR"
    DEFAULT_CONFIG_DIR = "~/.config/opencode"

    def bridge(self, installation: Installation) -> None:
        """One link: OpenCode's global AGENTS.md becomes ours."""
        installation.symlink(installation.agents_file, self.config_dir / "AGENTS.md")

    def unbridge(self, installation: Installation) -> None:
        """Remove that link when it is ours."""
        agents_file = self.config_dir / "AGENTS.md"
        if installation.owned(agents_file):
            agents_file.unlink()

    def default_config_dir(self) -> Path:
        return Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser() / "opencode"


AGENTS: tuple[Agent, ...] = (ClaudeCode(), OpenCode())
