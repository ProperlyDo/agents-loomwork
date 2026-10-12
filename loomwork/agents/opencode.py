from __future__ import annotations

import os
from pathlib import Path

from loomwork.agents.base import EnvConfiguredAgent
from loomwork.installation import Installation


class OpenCode(EnvConfiguredAgent):
    """Instruction follower: reads the global AGENTS.md and routes itself to the rule files at runtime — one link is the whole integration."""

    NAME = "opencode"

    CONFIG_DIR_ENV = "OPENCODE_CONFIG_DIR"
    DEFAULT_CONFIG_DIR = "~/.config/opencode"

    def bridge(self, installation: Installation) -> None:
        """One link: OpenCode's global AGENTS.md becomes ours."""
        installation.copy_rule(installation.agents_file, self.config_dir / "AGENTS.md")

    def unbridge(self, installation: Installation) -> None:
        """Remove that link when it is ours."""
        agents_file = self.config_dir / "AGENTS.md"
        if installation.owned(agents_file):
            agents_file.unlink()

    def default_config_dir(self) -> Path:
        return Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser() / "opencode"
