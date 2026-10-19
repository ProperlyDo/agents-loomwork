from __future__ import annotations

import os
from pathlib import Path

from loomwork.agents.base import Agent


class OpenCode(Agent):
    """Instruction follower: its global AGENTS.md sends it to the rules, since it loads no rules dir on its own."""

    NAME = "opencode"

    COMMAND = "opencode"
    AGENTS_MD_NAME = "AGENTS.md"

    @property
    def config_dir(self) -> Path:
        # the XDG spec's config root, where an empty value counts as unset — as it does for OpenCode
        return Path(os.environ.get("XDG_CONFIG_HOME") or "~/.config").expanduser() / "opencode"
