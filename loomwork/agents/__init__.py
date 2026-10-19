from __future__ import annotations

from pathlib import Path

from loomwork.agents.base import Agent
from loomwork.agents.claude_code import ClaudeCode
from loomwork.agents.opencode import OpenCode


def roster(claude_config_dir: Path) -> tuple[Agent, ...]:
    """Every supported agent, in the order a machine converges them — Claude in the config dir of this profile."""
    return (ClaudeCode(claude_config_dir), OpenCode())


__all__ = ["Agent", "ClaudeCode", "OpenCode", "roster"]
