from __future__ import annotations

from typing import TYPE_CHECKING

from loomwork import COMMAND_NAME, paths
from loomwork.output import info, warn
from loomwork.targets.declaration import Declaration

if TYPE_CHECKING:
    from pathlib import Path

    from loomwork.agents import Agent
    from loomwork.loom import Loom


class Sync:
    """Refresh one target dir from its sources, into every config dir it is wired from."""

    def __init__(
        self, loom: Loom, target_dir: Path, asking: Agent | None = None, *, sources_fresh: bool = False
    ) -> None:
        self.loom = loom
        self.target_dir = target_dir
        # the agent whose session hook asked, in the dir that session reads
        self.asking = asking
        # a machine-wide pass updates every source once before it syncs each target dir
        self.sources_fresh = sources_fresh

    def run(self) -> None:
        agents = self._without_conflicts(self._agents_wired_here())
        # a source added to the declaration since the last run is added here, so a pull is all a teammate needs
        self.loom.sources.add_declared(self.target_dir)
        self._bring_sources_up_to_date(agents)
        report = self.loom.wire(self.target_dir, agents)
        info(str(report))
        self._ask_for_a_restart(report.updated)

    def _bring_sources_up_to_date(self, agents: tuple[Agent, ...]) -> None:
        """Every source this sync copies from: the target dir's own, and each wired dir's."""
        # an opted-out target dir is only unwired, which needs no source
        if self.sources_fresh or Declaration.read(self.target_dir) is None:
            return
        keys = [
            *self.loom.sources.declared_keys(self.target_dir),
            *(key for agent in agents for key in self.loom.sources.keys_of(agent.config_dir)),
        ]
        self.loom.sources.refresh(list(dict.fromkeys(keys)))

    @staticmethod
    def _ask_for_a_restart(updated: tuple[Path, ...]) -> None:
        if not updated:
            return
        # an open session read what was here at its launch
        info(
            f"updated {', '.join(paths.shown(directory) for directory in updated)} — restart any open session to load it"
        )

    def _agents_wired_here(self) -> list[Agent]:
        """The agents the target dir is wired for, plus the one whose session runs here when it still declares."""
        wired = list(self.loom.wired_agents(self.target_dir))
        if self.asking is None or Declaration.read(self.target_dir) is None:
            return wired
        same_kind = self.asking.counterpart_in(tuple(wired))
        if same_kind is None:
            return [*wired, self.asking]
        if not any(agent.shares_dir_with(self.asking) for agent in wired):
            info(
                f"{paths.shown(self.target_dir)} is wired for {self.asking.NAME} from {paths.shown(same_kind.config_dir)}\n"
                f"  {same_kind.launch_hint()} to read its global rules"
            )
        # not adding the asking agent, since wiring it here too would hand this target dir to two setups
        return wired

    def _without_conflicts(self, wired: list[Agent]) -> tuple[Agent, ...]:
        """Leave out an agent wired from two of its dirs, since syncing both would have them clear each other's files."""
        names = [agent.NAME for agent in wired]
        conflicting = {name for name in names if names.count(name) > 1}
        for name in sorted(conflicting):
            # one line, since a session hook shows only the first
            config_dirs = ", ".join(paths.shown(agent.config_dir) for agent in wired if name == agent.NAME)
            warn(
                f"{paths.shown(self.target_dir)} is wired for {name} from {config_dirs} — "
                f"run '{COMMAND_NAME} init' in it to keep one"
            )
        return tuple(agent for agent in wired if agent.NAME not in conflicting)
