from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

import click

from loomwork import COMMAND_NAME
from loomwork.agents import SUPPORTED_AGENTS
from loomwork.cli.interview import InitInterview
from loomwork.errors import LoomError
from loomwork.loom import Loom
from loomwork.output import error
from loomwork.registry import Registry

Decorated = TypeVar("Decorated", bound=Callable)


def _resolved_target_dir(target_dir: Path | None) -> Path:
    return (target_dir or Path.cwd()).resolve()


def _config_dir_options(command: Decorated) -> Decorated:
    """One --<agent>-config-dir per supported agent, so a new agent brings its own flag."""
    # click lists the options last applied first
    for kind in reversed(SUPPORTED_AGENTS):
        command = click.option(
            kind.config_dir_option(),
            kind.NAME,
            type=click.Path(file_okay=False, path_type=Path),
            help=f"{kind.NAME}'s config dir, instead of ${kind.CONFIG_DIR_ENV} or its standard one.",
        )(command)
    return command


class LoomCommands(click.Group):
    """Our command group: a refusal from loom prints as one error line instead of click's traceback."""

    def invoke(self, context: click.Context) -> object:
        try:
            return super().invoke(context)
        except LoomError as refusal:
            error(str(refusal))


@click.group(COMMAND_NAME, cls=LoomCommands)
@_config_dir_options
@click.pass_context
def cli(context: click.Context, **config_dirs: Path | None) -> None:
    """Weave shared agent rules through your target dirs."""
    context.obj = Loom(Registry.at_home(), {name: config_dir for name, config_dir in config_dirs.items() if config_dir})


@cli.command()
@click.argument("target_dir", required=False, type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "--agents", "agent_names", metavar="NAMES", help="Comma-separated agents to wire, instead of being asked."
)
@click.option(
    "--source",
    help="Where the rules come from: a checkout, or <host>/<owner>/<repo>. Asked for when nothing else names one.",
)
@click.pass_obj
def init(loom: Loom, target_dir: Path | None, agent_names: str | None, source: str | None) -> None:
    """Wire TARGET_DIR, and set up the config dir of each agent it is wired for.

    TARGET_DIR defaults to the current directory.
    """
    target = _resolved_target_dir(target_dir)
    answers = InitInterview(loom, target, agent_names, source).run()
    loom.init(target, answers.agents, answers.source, answers.declaration, answers.ignore_generated)


@cli.command()
@click.argument("target_dir", required=False, type=click.Path(file_okay=False, path_type=Path))
@click.pass_obj
def remove(loom: Loom, target_dir: Path | None) -> None:
    """Unwire TARGET_DIR, undoing what loom put there.

    TARGET_DIR defaults to the current directory.
    """
    loom.remove(_resolved_target_dir(target_dir))


@cli.command()
@click.argument("target_dir", required=False, type=click.Path(file_okay=False, path_type=Path))
@click.option("--all", "everywhere", is_flag=True, help="Refresh every wired target dir instead of this one.")
@click.option("--for", "asked_by", metavar="NAME", help="The agent asking, as its session hook does.")
@click.pass_obj
def sync(loom: Loom, target_dir: Path | None, everywhere: bool, asked_by: str | None) -> None:
    """Refresh TARGET_DIR from its sources, into every config dir it is wired from.

    TARGET_DIR defaults to the current directory.
    """
    if everywhere:
        loom.sync_all()
        return
    asking = None
    if asked_by:
        asking = loom.agents_named((asked_by,))[0]
    loom.sync(_resolved_target_dir(target_dir), asking)


@cli.command()
@click.pass_obj
def status(loom: Loom) -> None:
    """Show each config dir loom writes into: its sources and its target dirs."""
    loom.status()


@cli.command()
@click.pass_obj
def uninstall(loom: Loom) -> None:
    """Undo everything loom installed, in every config dir."""
    loom.uninstall()
