from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from loomwork import AGENTS_DIR, TOOL_NAME


@dataclass(frozen=True)
class Registry:
    """What this machine knows: where the rules come from, and which projects asked for them."""

    path: Path = AGENTS_DIR / f".{TOOL_NAME}.json"

    VERSION: ClassVar[int] = 1

    def read(self) -> dict:
        if not self.path.is_file():
            return {"version": self.VERSION, "source": None, "namespace": None, "namespaces": [], "projects": {}}
        state = json.loads(self.path.read_text())
        # projects were a bare list before they recorded which tools they were wired for
        if isinstance(state.get("projects"), list):
            state["projects"] = {project: [] for project in state["projects"]}
        return state

    def write(self, state: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(state, indent=2) + "\n")

    def remember_source(self, source: Path, namespace: str) -> None:
        state = self.read()
        state["source"] = str(source)
        state["namespace"] = namespace
        self.write(state)
        self.remember_namespace(namespace)

    def remember_namespace(self, namespace: str) -> None:
        """Keep every name this machine has wired under, so a rename can still find the containers it left behind."""
        state = self.read()
        known = state.get("namespaces", [])
        if namespace in known:
            return
        state["namespaces"] = [*known, namespace]
        self.write(state)

    @property
    def namespaces(self) -> list[str]:
        return self.read().get("namespaces", [])

    @property
    def source(self) -> Path | None:
        remembered = self.read()["source"]
        return Path(remembered) if remembered else None

    @property
    def namespace(self) -> str | None:
        return self.read()["namespace"]

    @property
    def projects(self) -> list[Path]:
        return [Path(project) for project in self.read()["projects"]]

    def agents_for(self, project_dir: Path) -> list[str]:
        """The tools this project was wired for — empty when it predates the question, or was never added."""
        return self.read()["projects"].get(str(project_dir), [])

    def add(self, project_dir: Path, agents: list[str] | None = None) -> bool:
        """Remember a project and the tools it was wired for; False when nothing changed, so callers can stay quiet."""
        state = self.read()
        known = state["projects"].get(str(project_dir))
        wanted = agents if agents is not None else known or []
        if known == wanted:
            return False
        state["projects"][str(project_dir)] = wanted
        self.write(state)
        return True

    def drop(self, project_dir: Path) -> bool:
        state = self.read()
        if str(project_dir) not in state["projects"]:
            return False
        del state["projects"][str(project_dir)]
        self.write(state)
        return True

    def forget(self) -> None:
        self.path.unlink(missing_ok=True)
