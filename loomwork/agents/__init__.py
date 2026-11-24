from __future__ import annotations

from loomwork.agents.base import Agent
from loomwork.agents.claude_code import ClaudeCode
from loomwork.agents.opencode import OpenCode

# every supported agent, in the order a machine converges them
SUPPORTED_AGENTS: tuple[type[Agent], ...] = (ClaudeCode, OpenCode)


def kind_named(name: str) -> type[Agent]:
    """The supported agent class that goes by this name."""
    return next(kind for kind in SUPPORTED_AGENTS if name == kind.NAME)


__all__ = ["SUPPORTED_AGENTS", "Agent", "ClaudeCode", "OpenCode", "kind_named"]
