from __future__ import annotations

import re
import subprocess
import sys
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from loomwork import AGENTS_DIR, COMMAND_NAME, SOURCES_DIR, TOOL_NAME
from loomwork.declaration import Declaration

if TYPE_CHECKING:
    from loomwork.agents import Agent


def say(message: str) -> None:
    print(f"{COMMAND_NAME}: {message}")


def warn(message: str) -> None:
    print(f"{COMMAND_NAME}: {message}", file=sys.stderr)


def rmdir_quiet(directory: Path) -> None:
    with suppress(OSError):
        directory.rmdir()


@dataclass(frozen=True)
class Wiring:
    """What a pass over one project did — the caller reports it, so the decision is made in one place."""

    project_dir: Path
    declaration: Declaration | None
    wired: bool = False

    def __str__(self) -> str:
        if self.wired:
            return f"wired {self.project_dir} ({', '.join(self.declaration.rules)})"
        if self.declaration is None:
            return f"nothing wired — no {Declaration.FILE_NAME} in {self.project_dir}"
        return f"nothing wired — {self.project_dir} asks for the '{self.declaration.namespace}' rules"


@dataclass(frozen=True)
class Installation:
    """The agent-agnostic substrate — agents dir, project containers, link primitives. Agents only bridge into it, never build it."""

    namespace: str
    source: Path
    agents_dir: Path = AGENTS_DIR
    # what a project's hook line calls; the entry point resolves it, so a moved install rewrites itself on the next add
    tool_command: str = COMMAND_NAME
    # names this machine wired under before; their containers are ours to clear, a stranger's is not
    former_namespaces: tuple[str, ...] = ()

    REACH_GLOBAL_RE: ClassVar[re.Pattern] = re.compile(r"^reach:\s*global\s*$")
    # Claude reads the project's AGENTS.md itself, so nothing lays this shape any more — owning it still prunes the containers that carry one
    PROJECT_MD_TARGET: ClassVar[str] = "../../../AGENTS.md"
    # what marks a project copy as ours; trailing, so the rule's own frontmatter keeps line one
    COPY_MARKER: ClassVar[str] = f"<!-- written by {TOOL_NAME} -->"
    # copies on machines installed before the rename still carry this one, and must stay ours to be pruned
    COPY_MARKER_BEFORE_RENAME: ClassVar[str] = "<!-- written by agents-config -->"
    PULL_TIMEOUT_SECONDS: ClassVar[int] = 8

    def initialize(self, agents: tuple[Agent, ...]) -> None:
        """Once per machine: converge the agents dir and every present tool's bridges."""
        bridged = [agent for agent in agents if agent.present()]
        for agent in bridged:
            agent.forget_machine_hook(self)
        if not self.pull():
            warn("could not pull — using the source as it stands")
        self.converge(agents)
        say(f"source '{self.namespace}' from {self.source} into {self.agents_dir}")
        if bridged:
            say(f"bridged {', '.join(type(agent).__name__ for agent in bridged)}")
        else:
            warn("no agent config dirs found — nothing bridged; rerun after an agent's first launch")

    def wire(self, project_dir: Path, agents: tuple[Agent, ...]) -> Wiring:
        """Converge the agents dir and bridges, then wire one project — the whole of what a sync does for it."""
        self.converge(agents)
        return self.wire_project(project_dir, agents)

    def converge(self, agents: tuple[Agent, ...]) -> None:
        """Populate the agents dir and lay every present agent's bridges."""
        self.populate_agents_dir()
        for agent in agents:
            if agent.present():
                agent.bridge(self)

    def tear_down(self, agents: tuple[Agent, ...]) -> None:
        """Remove the machine-wide half: every bridge, then the agents-dir content we own."""
        # bridges first, then the agents dir they point into
        for agent in agents:
            agent.forget_machine_hook(self)
            agent.unbridge(self)
        self.prune(self.rules_dir, set())
        rmdir_quiet(self.rules_dir)
        rmdir_quiet(self.agents_dir / "rules")
        if self.owned(self.agents_file):
            self.agents_file.unlink()
        rmdir_quiet(self.agents_dir)
        say(f"uninstalled from {self.agents_dir} and every bridged agent — the clone at {self.source} remains")

    def populate_agents_dir(self) -> None:
        """Land AGENTS.md and every rule in the agents dir — the one place agent dirs read from."""
        self.reconcile(self.by_name(self.shipped_rule_files()), self.rules_dir)
        self.copy_rule(self.source / "AGENTS.md", self.agents_file)

    def wire_project(self, project_dir: Path, agents: tuple[Agent, ...]) -> Wiring:
        """Materialize the container in .agents/rules and let each agent bridge it; a missing declaration unwires."""
        container = project_dir / ".agents" / "rules" / self.namespace
        declaration = Declaration.read(project_dir)
        if declaration is None:
            # a removed declaration is the opt-out — everything we placed goes with it
            self.unwire_project(project_dir, agents)
            return Wiring(project_dir, None)
        if declaration.namespace != self.namespace:
            # the project asked for someone else's rules; leaving it alone is not the same as unwiring it
            return Wiring(project_dir, declaration)
        container.mkdir(parents=True, exist_ok=True)
        written = {}
        for name in declaration.rules:
            rule_file = self.rules_dir / f"{name}.md"
            if not rule_file.is_file():
                warn(f"unknown rule '{name}' in {project_dir / Declaration.FILE_NAME}")
                continue
            written[rule_file.name] = self.copy_rule(rule_file, container / rule_file.name)
        pruned = self.prune(container, set(written))
        # .claude/rules reaches every namespace dir in .agents/rules, so a rename would leave the old rules loading too
        pruned |= self.drop_former_containers(project_dir)
        if pruned or any(written.values()):
            # the hosting session collected its rules before this hook rewrote them — only a restart picks them up
            say("rules changed — restart the session to load them")
        for agent in agents:
            if agent.present():
                agent.bridge_project(self, project_dir)
        return Wiring(project_dir, declaration, wired=True)

    def drop_former_containers(self, project_dir: Path) -> bool:
        """Clear containers this machine left under a name it no longer uses. True when one went."""
        dropped = False
        for former in self.former_namespaces:
            container = project_dir / ".agents" / "rules" / former
            # prune takes only what carries our marker, so a foreign file in there keeps the directory alive
            dropped |= self.prune(container, set())
            rmdir_quiet(container)
        return dropped

    def unwire_project(self, project_dir: Path, agents: tuple[Agent, ...]) -> None:
        """Drop our container and every agent's per-project pointers."""
        self.drop_former_containers(project_dir)
        agents_rules_dir = project_dir / ".agents" / "rules"
        # a prune with no keep-set removes everything of ours
        self.prune(agents_rules_dir / self.namespace, set())
        rmdir_quiet(agents_rules_dir / self.namespace)
        rmdir_quiet(agents_rules_dir)
        for agent in agents:
            agent.unbridge_project(self, project_dir)

    def frontmatter(self, markdown_file: Path) -> list[str]:
        """The lines between the leading --- fences — body text never reads as configuration."""
        if not markdown_file.is_file():
            return []
        lines = markdown_file.read_text().splitlines()
        if not lines or lines[0].strip() != "---":
            return []
        for position, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                return lines[1:position]
        return []

    def pull(self) -> bool:
        """Fast-forward the clone, reporting whether it worked — the session hook stays silent, install speaks up."""
        # macOS ships no timeout(1); subprocess provides the bound the hook otherwise had to enforce
        try:
            pulled = subprocess.run(
                ["git", "-C", str(self.source), "pull", "--ff-only", "--quiet"],
                timeout=self.PULL_TIMEOUT_SECONDS,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return False
        return pulled.returncode == 0

    def reconcile(self, wanted: dict[str, Path | str], into_dir: Path) -> bool:
        """Put every entry in the dir under its given name and prune what no longer belongs. A Path is copied in, a string is the target of a link."""
        into_dir.mkdir(parents=True, exist_ok=True)
        changed = False
        for name, target in wanted.items():
            if isinstance(target, Path):
                changed |= self.copy_rule(target, into_dir / name)
            else:
                changed |= self.symlink(target, into_dir / name)
        return self.prune(into_dir, set(wanted)) or changed

    def by_name(self, sources: list[Path]) -> dict[str, Path]:
        """Sources keyed by the name they keep in the destination dir."""
        return {source.name: source for source in sources}

    def symlink(self, target: Path | str, link_path: Path) -> bool:  # argument order mirrors ln -s
        """Create the link unless the name is taken by something we don't own — then warn and step aside. True when the link now points somewhere new."""
        if (link_path.exists() or link_path.is_symlink()) and not self.owned(link_path):
            warn(f"{link_path} exists and is not ours — skipped")
            return False
        # read before the unlink below erases the evidence — callers report what the running session never saw
        was = str(link_path.readlink()) if link_path.is_symlink() else None
        link_path.unlink(missing_ok=True)
        # a concurrent sync may win the unlink-to-create window, and its link is identical
        with suppress(FileExistsError):
            link_path.symlink_to(target)
        return was != str(target)

    def copy_rule(self, source: Path, destination: Path) -> bool:
        """Write the rule into the project. A link here resolves outside it, and Claude gates those behind an approval only an @path import can raise. True when the project's copy now reads differently."""
        taken = destination.exists() or destination.is_symlink()
        if taken and not self.owned(destination):
            warn(f"{destination} exists and is not ours — skipped")
            return False
        rule = f"{source.read_text().rstrip()}\n\n{self.COPY_MARKER}\n".encode()
        # a link from the era before copies counts as changed — its content never was in this session
        was = destination.read_bytes() if taken and not destination.is_symlink() else None
        # unlink before writing — a stale link here would send the write into the clone
        destination.unlink(missing_ok=True)
        destination.write_bytes(rule)
        return was != rule

    def prune(self, scan_dir: Path, keep: set[str]) -> bool:
        """Remove what we own whose name left the keep-set — upstream renames and deletions leave no zombies. True when something went."""
        if not scan_dir.is_dir():
            return False
        pruned = False
        for entry in list(scan_dir.iterdir()):
            if self.owned(entry) and entry.name not in keep:
                entry.unlink(missing_ok=True)
                pruned = True
        return pruned

    def owned(self, path: Path) -> bool:
        """Ours when it carries our marker, lands in this clone, or wears one of our project-relative shapes."""
        if not path.is_symlink():
            return self.is_our_copy(path)
        if str(path.readlink()) in self.project_shapes():
            return True
        # a link resolving to nothing is nobody's, and a moved source leaves ours looking foreign otherwise
        if not path.exists():
            return True
        # our namespace's staging dir, never the whole agents dir: a second installation's links must stay foreign
        landed = path.resolve()
        # a clone under SOURCES_DIR is one we fetched, so links into it stay ours after `init` repoints the machine
        return any(landed.is_relative_to(ours) for ours in (self.source, self.rules_dir, SOURCES_DIR))

    @classmethod
    def project_shapes(cls) -> frozenset[str]:
        """Every relative link shape we own inside a project: our own container's, plus whatever each agent lays."""
        # the agents import Installation, so this one stays function-local to break that cycle
        from loomwork.agents import AGENTS  # noqa: PLC0415

        return frozenset({cls.PROJECT_MD_TARGET, *(shape for agent in AGENTS for shape in agent.PROJECT_SHAPES)})

    def is_our_copy(self, path: Path) -> bool:
        """A rule we wrote into a project — the marker is what ownership rests on once there is no link target to read."""
        try:
            content = path.read_text(errors="replace")
        except OSError:
            return False
        return content.rstrip().endswith((self.COPY_MARKER, self.COPY_MARKER_BEFORE_RENAME))

    def is_stack_neutral(self, rule_file: Path) -> bool:
        """`reach: global` is the opt-in; every other rule reaches only the projects that declare its stack."""
        return any(self.REACH_GLOBAL_RE.match(line) for line in self.frontmatter(rule_file))

    def shipped_rule_files(self) -> list[Path]:
        return sorted((self.source / "rules").glob("*.md"))

    @property
    def rules_dir(self) -> Path:
        return self.agents_dir / "rules" / self.namespace

    @property
    def agents_file(self) -> Path:
        return self.agents_dir / "AGENTS.md"
