from __future__ import annotations

from loomwork.agents.base import Agent, EnvConfiguredAgent
from loomwork.agents.claude_code import ClaudeCode
from loomwork.agents.jetbrains import JetBrains
from loomwork.agents.opencode import OpenCode

# the roster, in the order a machine converges them
AGENTS: tuple[Agent, ...] = (ClaudeCode(), OpenCode(), JetBrains())

__all__ = ["AGENTS", "Agent", "ClaudeCode", "EnvConfiguredAgent", "JetBrains", "OpenCode"]
