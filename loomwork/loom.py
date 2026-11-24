from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property
from typing import TYPE_CHECKING

from loomwork import COMMAND_NAME, paths
from loomwork.agents import SUPPORTED_AGENTS, Agent, kind_named
from loomwork.errors import LoomError
from loomwork.installation import Installation
from loomwork.output import info, warn
from loomwork.sources.fetched import FetchedSources
from loomwork.targets.declaration import Declaration
from loomwork.targets.gitignore import Gitignore
from loomwork.targets.sync import Sync
from loomwork.targets.wiring import Wiring, WiringReport
from loomwork.validators import validate_agent_names

if TYPE_CHECKING:
    from pathlib import Path

    from loomwork.registry import Registry


@dataclass(frozen=True)
class Loom:
    """What loom does for every config dir it writes into: the sources pinned to each, and the target dirs wired from it."""

    registry: Registry
    # per agent name, the config dir the command line gave it, which beats the agent's launch variable
    cli_config_dirs: dict[str, Path] = field(default_factory=dict)

    def init(
        self,
        target_dir: Path,
        agents: tuple[Agent, ...],
        source: str | None = None,
        declaration: Declaration | None = None,
        ignore_generated: bool = False,
    ) -> None:
        """Declare the target dir if asked, set up the chosen agents' config dirs, and wire it when it is declared."""
        self._require_a_source(target_dir, agents, source, declaration)
        self._record_config_dirs(agents)
        # fetched before the target dir is written to, so a source that cannot be reached leaves it untouched
        self._pin_source(agents, source)
        self._declare(target_dir, declaration)
        if ignore_generated:
            Gitignore(target_dir, self.agents).add_ours()
        self.sources.add_declared(target_dir)
        self._lay_global_files(target_dir, agents)
        self._warn_about_absent_agents(agents)
        if Declaration.read(target_dir) is None:
            warn(f"{target_dir} carries no {Declaration.FILE_NAME}, so nothing is wired there yet")
            return
        self._add_target_dir(target_dir, agents)

    def remove(self, target_dir: Path) -> None:
        wired = self.wired_agents(target_dir)
        # a target dir loom has no record of may still hold links an earlier setup laid
        self._unwire(target_dir, wired or self.agents)
        for agent in wired:
            self._drop_from(agent, target_dir)
        if wired:
            info(f"dropped {target_dir}")
        else:
            warn(f"{target_dir} was not wired — unwired it anyway")

    def sync(self, target_dir: Path, asking: Agent | None = None) -> None:
        """Refresh one target dir into every config dir it is wired from."""
        # a known target dir without its declaration has opted out, which a sync still has to undo
        if Declaration.read(target_dir) is None and not self.wired_agents(target_dir):
            warn(f"{target_dir} carries no {Declaration.FILE_NAME} — nothing to sync")
            return
        Sync(self, target_dir, asking).run()

    def sync_all(self) -> None:
        """The machine-wide pass: every source updated once, then every wired target dir."""
        if not self.registry.target_dirs:
            info(f"no target dirs yet — '{COMMAND_NAME} init' takes one on")
            return
        self.sources.refresh(self.registry.source_keys)
        for target_dir in self.registry.target_dirs:
            try:
                self._sync_or_drop(target_dir)
            except LoomError as refusal:
                # one broken target dir must not leave the ones after it unsynced
                warn(f"{target_dir}: {refusal}")

    def status(self) -> None:
        config_dirs = self.registry.config_dirs()
        if not config_dirs:
            info(f"nothing set up yet — '{COMMAND_NAME} init' in a target dir takes one on")
        for config_dir in config_dirs:
            self._report_config_dir(config_dir)

    def uninstall(self) -> None:
        """Undo everything loom installed: every target dir, then every config dir and the registry."""
        for target_dir in self.registry.target_dirs:
            if target_dir.is_dir():
                self._unwire(target_dir, self.wired_agents(target_dir))
        # every config dir, the agent installed or not, since loom writes for an agent before it is installed
        for config_dir in self.registry.config_dirs():
            self._get_agent(config_dir).clear_global_files(self.installation_of([]))
        info(f"cleared every agent's global files — the clones in {paths.SOURCES_DIR} remain")
        self.registry.forget()

    def wire(self, target_dir: Path, agents: tuple[Agent, ...]) -> WiringReport:
        """Wire one target dir from each agent's dir, or undo it once its declaration is gone."""
        declaration = Declaration.read(target_dir)
        if declaration is None:
            return self._unwire_opted_out(target_dir)
        return Wiring(self, target_dir, declaration, agents).run()

    def installation_of(self, keys: list[str], updated: list[Path] | None = None) -> Installation:
        """These sources as something that can act, noting the directories it changes in updated."""
        if updated is None:
            updated = []
        return Installation(catalog=self.sources.catalog_of(keys), registry=self.registry, updated=updated)

    def lacks_a_source(self, agents: tuple[Agent, ...]) -> bool:
        """Whether a chosen agent's dir draws on no source yet, pinned or declared by its target dirs."""
        return any(not self.sources.keys_of(agent.config_dir) for agent in agents)

    def agents_named(self, names: tuple[str, ...]) -> tuple[Agent, ...]:
        """The agents behind the names a caller picked, each in the dir this run gives it — loom touches these and no others."""
        validate_agent_names(names)
        return tuple(agent for agent in self.agents if agent.NAME in names)

    def wired_agents(self, target_dir: Path) -> tuple[Agent, ...]:
        """The agents a target dir is wired for, each in the dir it is wired from."""
        return tuple(self._get_agent(config_dir) for config_dir in self.registry.config_dirs_of(target_dir))

    def wired_elsewhere(self, target_dir: Path, agents: tuple[Agent, ...]) -> tuple[Agent, ...]:
        """The chosen agents' other dirs this target dir is wired from."""
        moved = []
        for wired in self.wired_agents(target_dir):
            chosen = wired.counterpart_in(agents)
            if chosen is not None and not wired.shares_dir_with(chosen):
                moved.append(wired)
        return tuple(moved)

    def usual_agents(self, target_dir: Path) -> tuple[str, ...]:
        """What a target dir is likely wired for: what it was set up for, or on a first run whatever is installed here."""
        wired = self.wired_agents(target_dir)
        if wired:
            return tuple(agent.NAME for agent in wired)
        return tuple(agent.NAME for agent in self.installed_agents())

    def installed_agents(self) -> tuple[Agent, ...]:
        return tuple(agent for agent in self.agents if agent.is_present())

    def most_declared_source(self) -> str | None:
        """The source most target dirs here declare — the likely answer for one more of the same."""
        declarations = [Declaration.read(target_dir) for target_dir in self.registry.target_dirs if target_dir.is_dir()]
        declared = [entry.source for declaration in declarations if declaration for entry in declaration.sources]
        return max(declared, key=declared.count, default=None)

    def _require_a_source(
        self, target_dir: Path, agents: tuple[Agent, ...], source: str | None, declaration: Declaration | None
    ) -> None:
        """Refuse before anything is written when no chosen agent's dir would have rules to lay."""
        if source or declaration or Declaration.read(target_dir) or not self.lacks_a_source(agents):
            return
        raise LoomError("no_source", f"no source yet — run '{COMMAND_NAME} init --source <path-to-rules-repo>'")

    def _declare(self, target_dir: Path, declaration: Declaration | None) -> None:
        """Write the target dir's opt-in: which sources it uses, and what it takes from each."""
        if declaration is None:
            return
        info(f"declared {declaration.write(target_dir)}")
        if not declaration.rules and not declaration.skills:
            warn("nothing declared — this target dir gets only what its sources hand every target dir")

    def _record_config_dirs(self, agents: tuple[Agent, ...]) -> None:
        for agent in agents:
            self.registry.add_config_dir(agent.config_dir, agent.NAME)

    def _pin_source(self, agents: tuple[Agent, ...], source: str | None) -> None:
        """The source passed to init with --source, pinned to the agents' dirs."""
        if source:
            self.sources.add(source, pinned_to=tuple(agent.config_dir for agent in agents))

    def _lay_global_files(self, target_dir: Path, agents: tuple[Agent, ...]) -> None:
        """Each agent's global files, saying where they landed and how to launch the agent to read them."""
        self.sources.warn_about_gone(
            list(dict.fromkeys(key for agent in agents for key in self.sources.keys_of(agent.config_dir)))
        )
        for agent in agents:
            # the target dir's own sources count before it is wired, so its global rules land in this same run
            keys = [*self.sources.keys_of(agent.config_dir), *self.sources.declared_keys(target_dir)]
            laid = agent.lay_global_files(self.installation_of(keys))
            if laid:
                info("\n".join([f"wired {agent.NAME}", *(f"  {paths.shown(path)}" for path in laid)]))
            note = agent.launch_note()
            if note:
                info(note)

    def _add_target_dir(self, target_dir: Path, agents: tuple[Agent, ...]) -> None:
        """Wire a target dir for exactly the chosen agents, each from the dir this run gives it."""
        self.sources.add_declared(target_dir)
        self._unwire_unchosen(target_dir, agents)
        self._move_off_other_config_dirs(target_dir, agents)
        info(str(self.wire(target_dir, agents)))

    def _unwire_unchosen(self, target_dir: Path, agents: tuple[Agent, ...]) -> None:
        for wired in self.wired_agents(target_dir):
            if wired.counterpart_in(agents) is None:
                wired.unwire_target_dir(self.installation_of([]), target_dir)
                self._drop_from(wired, target_dir)
                info(f"unwired {wired.NAME} from {target_dir}")

    def _move_off_other_config_dirs(self, target_dir: Path, agents: tuple[Agent, ...]) -> None:
        for wired in self.wired_elsewhere(target_dir, agents):
            self._drop_from(wired, target_dir)
            moved_to = wired.counterpart_in(agents)
            info(f"moved {wired.NAME} from {paths.shown(wired.config_dir)} to {paths.shown(moved_to.config_dir)}")

    def _warn_about_absent_agents(self, agents: tuple[Agent, ...]) -> None:
        absent = [agent.NAME for agent in agents if not agent.is_present()]
        if absent:
            warn(f"{', '.join(absent)} is not installed here — its files are written where it will look for them")

    def _sync_or_drop(self, target_dir: Path) -> None:
        """Sync a recorded target dir with the sources already fresh, or forget it once it is gone."""
        if not target_dir.is_dir():
            warn(f"{target_dir} is gone — dropping it")
            for wired in self.wired_agents(target_dir):
                self._drop_from(wired, target_dir)
            return
        Sync(self, target_dir, sources_fresh=True).run()

    def _report_config_dir(self, config_dir: Path) -> None:
        info(f"{self.registry.get_agent_name(config_dir)} {paths.shown(config_dir)}")
        keys = self.sources.keys_of(config_dir)
        for key in keys:
            info(f"  source {self.registry.source_of(key)}")
        # the one thing no target dir's declaration shows: what its sources hand out anyway
        catalog = self.sources.catalog_of(keys)
        for kind, names in (("rules", catalog.global_rules), ("skills", catalog.global_skills)):
            if names:
                info(f"  every target dir gets {kind}: {', '.join(names)}")
        for target_dir in self.registry.target_dirs_in(config_dir):
            info(f"  target dir {paths.shown(target_dir)}")

    def _unwire_opted_out(self, target_dir: Path) -> WiringReport:
        """A removed declaration is the opt-out — everything we placed goes with it, for every agent wired here."""
        self._unwire(target_dir, self.wired_agents(target_dir))
        for wired in self.wired_agents(target_dir):
            self._drop_from(wired, target_dir)
        return WiringReport(target_dir, None)

    def _drop_from(self, agent: Agent, target_dir: Path) -> None:
        """Forget the target dir in the agent's dir, and lay that dir's global files again without what only it brought."""
        self.registry.drop_target_dir(agent.config_dir, target_dir)
        agent.lay_global_files(self.installation_of(self.sources.keys_of(agent.config_dir)))

    def _unwire(self, target_dir: Path, agents: tuple[Agent, ...]) -> None:
        """Mirror of wire(): each agent's pointers, then our copies — rules and skills alike."""
        installation = self.installation_of([])
        for agent in agents:
            agent.unwire_target_dir(installation, target_dir)
        for placed_dir in (paths.target_rules_dir(target_dir), paths.target_skills_dir(target_dir)):
            installation.clear_owned_in(placed_dir)
            paths.remove_if_empty(placed_dir)
        paths.remove_if_empty(target_dir / paths.AGENTS_DIR_NAME)

    def _get_agent(self, config_dir: Path) -> Agent:
        """The agent a recorded config dir belongs to, in that dir."""
        return kind_named(self.registry.get_agent_name(config_dir))(config_dir)

    @property
    def agents(self) -> tuple[Agent, ...]:
        """Every supported agent, each in the dir this run gives it."""
        return tuple(kind.from_config_dir(self.cli_config_dirs.get(kind.NAME)) for kind in SUPPORTED_AGENTS)

    @cached_property
    def sources(self) -> FetchedSources:
        return FetchedSources(self.registry)
