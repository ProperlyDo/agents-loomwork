#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

import click

from loomwork import COMMAND_NAME, valid_namespace
from loomwork.agents import Agent
from loomwork.loom import Loom


def namespace_word(context: click.Context, parameter: click.Parameter, value: str | None) -> str | None:
    """A click callback, so a bad value is reported the way click reports every other one."""
    if value is not None and not valid_namespace(value):
        raise click.BadParameter("must be a single path-safe word")
    return value


def project_dir(project: Path | None) -> Path:
    return (project or Path.cwd()).resolve()


@click.group(COMMAND_NAME)
@click.option(
    "--namespace", callback=namespace_word, metavar="NAME", help="Act as this namespace instead of the registered one."
)
@click.pass_context
def cli(context: click.Context, namespace: str | None) -> None:
    """Weave shared agent rules through your projects."""
    # every command below takes this as its first argument, through @click.pass_obj
    context.obj = Loom(namespace=namespace)


@cli.command()
@click.argument("source", required=False, type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.pass_obj
def init(loom: Loom, source: Path | None) -> None:
    """Point this machine at the rules repo at SOURCE, defaulting to the current directory."""
    loom.point_at(project_dir(source))


@cli.command()
@click.argument("project", required=False, type=click.Path(file_okay=False, path_type=Path))
@click.option("--agents", "chosen", metavar="NAMES", help="Comma-separated tools to wire, instead of being asked.")
@click.pass_obj
def add(loom: Loom, project: Path | None, chosen: str | None) -> None:
    """Take PROJECT under management, defaulting to the current directory."""
    present = loom.present()
    if not present:
        raise SystemExit("no agent config dirs found — nothing to wire this project for")
    loom.add(project_dir(project), chosen_agents(present, chosen))


def chosen_agents(present: tuple[Agent, ...], chosen: str | None) -> tuple[str, ...]:
    """Which tools to wire: the flag when given, the answer when a person can be asked, everything present otherwise."""
    names = [agent.NAME for agent in present]
    if chosen:
        picked = [name.strip() for name in chosen.split(",") if name.strip()]
        unknown = [name for name in picked if name not in names]
        if unknown:
            raise click.BadParameter(f"not installed here: {', '.join(unknown)}. Present: {', '.join(names)}")
        return tuple(picked)
    if len(names) == 1 or not sys.stdin.isatty():
        return tuple(names)
    click.echo("Wire this project for:")
    for position, name in enumerate(names, start=1):
        click.echo(f"  {position}. {name}")
    answer = click.prompt("Numbers, comma-separated", default="all", show_default=True)
    if answer.strip() in ("all", ""):
        return tuple(names)
    try:
        return tuple(names[int(number.strip()) - 1] for number in answer.split(",") if number.strip())
    except (ValueError, IndexError):
        raise click.BadParameter(f"pick from 1-{len(names)}, or 'all'") from None


@cli.command()
@click.argument("project", required=False, type=click.Path(file_okay=False, path_type=Path))
@click.pass_obj
def remove(loom: Loom, project: Path | None) -> None:
    """Stop managing PROJECT and undo what we put there."""
    loom.remove(project_dir(project))


@cli.command()
@click.argument("project", required=False, type=click.Path(file_okay=False, path_type=Path))
@click.pass_obj
def sync(loom: Loom, project: Path | None) -> None:
    """Refresh PROJECT from the source, or every managed project when none is named."""
    # no project named means every registered one, so this must not fall back to the current directory
    loom.sync(project.resolve() if project else None)


@cli.command()
@click.pass_obj
def status(loom: Loom) -> None:
    """Show the source and the projects under management."""
    loom.status()


@cli.command()
@click.pass_obj
def uninstall(loom: Loom) -> None:
    """Undo everything this machine has installed."""
    loom.uninstall()


if __name__ == "__main__":
    cli()
