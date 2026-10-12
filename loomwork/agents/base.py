from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar

from loomwork.installation import Installation


class Agent(ABC):
    """A supported tool, integrated by overriding exactly the surfaces it can consume — the no-op defaults cover the rest.

    The shape of a subclass mirrors how the tool loads rules: a tool that reads and follows instructions
    needs only a global link (OpenCode); a tool with a mechanical loader selects by which files exist,
    so its class must also translate the project's declaration into filesystem state (ClaudeCode, JetBrains).
    """

    # the relative shapes this tool's project links wear; Installation owns a link only if some agent claims its shape
    PROJECT_SHAPES: ClassVar[frozenset[str]] = frozenset()
    # what a project records to say it wants this tool, and what the prompt offers
    NAME: ClassVar[str]

    @classmethod
    def offered_source(cls) -> Path | None:
        """Where this tool put the rules when it invoked us — a tool that ships none offers nothing."""
        return None

    @staticmethod
    def names_source(source: Path) -> str | None:
        """What that offered source calls itself, when it carries a name of its own."""
        return None

    def present(self) -> bool:
        """An agent that never ran gets nothing — config dirs are never fabricated for absent tools."""
        return self.config_dir.is_dir()

    @property
    @abstractmethod
    def config_dir(self) -> Path:
        """Where the tool keeps its own configuration — our presence marker, and for most the bridge target."""

    @abstractmethod
    def bridge(self, installation: Installation) -> None:
        """Lay this tool's links into its config dir, pointing at the installation's."""

    @abstractmethod
    def unbridge(self, installation: Installation) -> None:
        """Remove every link bridge() laid, touching nothing foreign."""

    def forget_machine_hook(self, installation: Installation) -> None:
        """A no-op unless the tool once carried a machine-wide hook of ours."""
        return

    def bridge_project(self, installation: Installation, project_dir: Path) -> None:
        """A no-op unless the tool keeps per-project state to point at the container."""
        return

    def unbridge_project(self, installation: Installation, project_dir: Path) -> None:
        """Mirror of bridge_project() — remove per-project pointers when the container is gone."""
        return


class EnvConfiguredAgent(Agent):
    """A tool that reads its config dir from an env var — point the tool elsewhere and our links follow it."""

    # each agent names the env var it honors — never invent one the tool itself doesn't read
    CONFIG_DIR_ENV: ClassVar[str]
    DEFAULT_CONFIG_DIR: ClassVar[str]

    @property
    def config_dir(self) -> Path:
        configured = os.environ.get(self.CONFIG_DIR_ENV)
        if configured:
            return Path(configured).expanduser()
        return self.default_config_dir()

    def default_config_dir(self) -> Path:
        """The override seam for computed defaults — OpenCode replaces this with its XDG fallback."""
        return Path(self.DEFAULT_CONFIG_DIR).expanduser()
