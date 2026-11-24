from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from loomwork import COMMAND_NAME, paths
from loomwork.cli import prompts
from loomwork.errors import LoomError
from loomwork.sources.manifest import Manifest
from loomwork.targets.declaration import Declaration, DeclaredSource
from loomwork.targets.gitignore import Gitignore
from loomwork.validators import validate_source

if TYPE_CHECKING:
    from pathlib import Path

    from loomwork.agents import Agent
    from loomwork.loom import Loom


@dataclass(frozen=True)
class InitAnswers:
    """What init was told, by flags or by the user, before it writes anything."""

    agents: tuple[Agent, ...]
    # pinned to the agents' dirs, so None when the declaration or the dirs already name one
    source: str | None
    # written into the target dir, so None when it already carries one or stays undeclared
    declaration: Declaration | None
    ignore_generated: bool


class InitInterview:
    """The questions init asks — each skipped when a flag, the target dir or what loom recorded already answers it."""

    def __init__(self, loom: Loom, target_dir: Path, agent_names: str | None, source: str | None) -> None:
        self.loom = loom
        self.target_dir = target_dir
        # the --agents and --source flags, which answer their questions up front
        self.agent_names = agent_names
        self.source = source

    def run(self) -> InitAnswers:
        agents = self._wanted_agents()
        self._confirm_moves(agents)
        declaration = self._wanted_declaration()
        source = self._wanted_source(agents, declaration)
        ignore_generated = self._wants_generated_ignored(declaration)
        return InitAnswers(agents, source, declaration, ignore_generated)

    def _wanted_agents(self) -> tuple[Agent, ...]:
        """Which agents this target dir is wired for — any we support, installed here or not."""
        if self.agent_names:
            return self.loom.agents_named(tuple(name.strip() for name in self.agent_names.split(",") if name.strip()))
        usual = self.loom.usual_agents(self.target_dir)
        if not prompts.can_ask():
            return self._agents_without_asking(usual)
        choices = [
            prompts.Choice(agent.NAME, note=self._presence_note(agent), ticked=agent.NAME in usual)
            for agent in self.loom.agents
        ]
        return self.loom.agents_named(prompts.pick("Wire this target dir for", choices, required=True))

    def _confirm_moves(self, agents: tuple[Agent, ...]) -> None:
        """Refuse unless the target dir may leave the other dirs it is wired from for these agents."""
        elsewhere = self.loom.wired_elsewhere(self.target_dir, agents)
        if not elsewhere:
            return
        moves = ", ".join(
            f"{agent.NAME} from {paths.shown(agent.config_dir)} to {paths.shown(agent.counterpart_in(agents).config_dir)}"
            for agent in elsewhere
        )
        if not prompts.can_ask():
            raise LoomError(
                "move_needs_a_terminal",
                f"{self.target_dir} would move {moves} — run '{COMMAND_NAME} init' from a terminal to move it",
            )
        if not prompts.confirm(f"Move {self.target_dir.name}: {moves}?"):
            raise LoomError("move_declined", f"{self.target_dir} stays wired where it is")

    def _wanted_declaration(self) -> Declaration | None:
        """What the target dir takes from a source — asked only when it declares nothing yet."""
        if Declaration.read(self.target_dir) or not prompts.can_ask():
            return None
        if not prompts.confirm(f"Declare {Declaration.FILE_NAME} in {self.target_dir.name}?"):
            return None
        source = self._ask_source(default=self.source or self.loom.most_declared_source() or "")
        # a relative path in the declaration counts from the target dir, so the offer reads it from there too
        catalog = self.loom.sources.offered_by(paths.resolved_from(source, self.target_dir))
        rules = prompts.pick(
            "Rules this target dir uses", self._source_choices(catalog.offered_rules, catalog.global_rules)
        )
        skills = prompts.pick(
            "Skills this target dir uses", self._source_choices(catalog.offered_skills, catalog.global_skills)
        )
        return Declaration((DeclaredSource(source=source, rules=rules, skills=skills),))

    def _wanted_source(self, agents: tuple[Agent, ...], declaration: Declaration | None) -> str | None:
        """A source for the agents' dirs — asked only when neither the flag, a declaration nor the dirs name one."""
        if self.source or declaration or Declaration.read(self.target_dir):
            return self.source
        if not self.loom.lacks_a_source(agents) or not prompts.can_ask():
            return None
        return self._ask_source()

    def _wants_generated_ignored(self, declaration: Declaration | None) -> bool:
        if declaration is None or not Gitignore(self.target_dir, self.loom.agents).unignored():
            return False
        return prompts.confirm(f"Update {Gitignore.FILE_NAME}?")

    def _agents_without_asking(self, usual: tuple[str, ...]) -> tuple[Agent, ...]:
        """What the target dir is wired for, or on a first run what is installed — refused when that is nothing."""
        if not usual:
            raise LoomError("no_agents", f"no agent to wire — run '{COMMAND_NAME} init --agents claude,opencode'")
        return self.loom.agents_named(usual)

    def _ask_source(self, default: str = "") -> str:
        return prompts.ask(
            "Where the rules come from (a checkout, or <host>/<owner>/<repo>)",
            default=default,
            check=self._source_check,
        )

    def _source_check(self, value: str) -> bool | str:
        """The source rule as the prompt applies it: True, or what to fix."""
        try:
            validate_source(paths.resolved_from(value.strip(), self.target_dir))
        except LoomError as refusal:
            return str(refusal)
        return True

    @staticmethod
    def _source_choices(offered: tuple[str, ...], handed_out: tuple[str, ...]) -> list[prompts.Choice]:
        """What a source offers, then what it hands out anyway — shown, but no choice."""
        locked_because = f"marked global in the source's {Manifest.FILE_NAME}"
        return [
            *(prompts.Choice(name) for name in offered),
            *(prompts.Choice(name, locked_because=locked_because) for name in handed_out),
        ]

    @staticmethod
    def _presence_note(agent: Agent) -> str:
        if agent.is_present():
            return ""
        return "not installed here"
