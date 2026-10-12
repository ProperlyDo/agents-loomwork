from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import ClassVar

from loomwork.agents.base import Agent
from loomwork.declaration import Declaration
from loomwork.installation import Installation, rmdir_quiet


class JetBrains(Agent):
    """Mechanical loader without a global channel: AI Assistant (PyCharm, WebStorm, …) reads rules per project only, so its project links must also carry the universal layer."""

    NAME = "jetbrains"

    # two hops up from .aiassistant/rules/ is the project root, where its own AGENTS.md sits
    ASSISTANT_MD_TARGET: ClassVar[str] = "../../AGENTS.md"
    PROJECT_SHAPES: ClassVar[frozenset[str]] = frozenset({ASSISTANT_MD_TARGET})

    def bridge(self, installation: Installation) -> None:
        """Nothing to lay — AI Assistant has no file-based user-level rules."""
        return

    def unbridge(self, installation: Installation) -> None:
        """Mirror of bridge() — nothing was laid."""
        return

    def bridge_project(self, installation: Installation, project_dir: Path) -> None:
        """Flat links in .aiassistant/rules — with no global channel, the project set carries everything: universal layer, global rules, the declared ones, the project's own file."""
        declaration = Declaration.read(project_dir)
        declared = declaration.rules if declaration else ()
        wanted = sorted(installation.rules_dir.glob("*.md"))
        our_rules = [
            installation.agents_file,
            *(rule for rule in wanted if installation.is_stack_neutral(rule) or rule.stem in declared),
        ]
        links = installation.by_name(our_rules)
        # project.md, because the universal layer already holds the AGENTS.md name here; a project without one gets no link
        if (project_dir / "AGENTS.md").is_file():
            links |= {"project.md": self.ASSISTANT_MD_TARGET}
        installation.reconcile(links, self.assistant_rules_dir(project_dir))

    def unbridge_project(self, installation: Installation, project_dir: Path) -> None:
        """Drop our rule links and the dirs when they empty out."""
        installation.prune(self.assistant_rules_dir(project_dir), set())
        rmdir_quiet(self.assistant_rules_dir(project_dir))
        rmdir_quiet(project_dir / ".aiassistant")

    def assistant_rules_dir(self, project_dir: Path) -> Path:
        return project_dir / ".aiassistant" / "rules"

    @property
    def config_dir(self) -> Path:
        # JetBrains reads no config-dir env var — the IDE support dir is just the presence marker
        if sys.platform == "darwin":
            return Path("~/Library/Application Support/JetBrains").expanduser()
        return Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser() / "JetBrains"
