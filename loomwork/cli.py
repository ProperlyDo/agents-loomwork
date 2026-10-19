#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

import click

from loomwork import COMMAND_NAME
from loomwork.agents import ClaudeCode
from loomwork.declaration import Declaration
from loomwork.loom import Loom
from loomwork.questions import declare_project, wanted_agents, wanted_config_dir, wanted_source


def project_dir(project: Path | None) -> Path:
    return (project or Path.cwd()).resolve()


def profile(config_dir: Path | None) -> Loom:
    """The profile the flag names, else the one in Claude's default config dir."""
    if config_dir:
        return Loom(config_dir.expanduser())
    return Loom(ClaudeCode.DEFAULT_CONFIG_DIR)


@click.group(COMMAND_NAME)
@click.option(
    "--config-dir",
    type=click.Path(file_okay=False, path_type=Path),
    help="Claude's config dir, which this profile lives in. Defaults to ~/.claude; init asks when it is left out.",
)
@click.pass_context
def cli(context: click.Context, config_dir: Path | None) -> None:
    """Weave shared agent rules through your projects."""
    context.obj = config_dir


@cli.command()
@click.argument("project", required=False, type=click.Path(file_okay=False, path_type=Path))
@click.option("--agents", "chosen", metavar="NAMES", help="Comma-separated agents to wire, instead of being asked.")
@click.option(
    "--source",
    "given_source",
    help="Where the rules come from: a checkout, or <host>/<owner>/<repo>. Asked for when nothing else names one.",
)
@click.pass_obj
def init(config_dir: Path | None, project: Path | None, chosen: str | None, given_source: str | None) -> None:
    """Wire PROJECT and set up this profile.

    PROJECT defaults to the current directory.
    """
    target = project_dir(project)
    # the profile first: everything below is written into it
    loom = Loom(wanted_config_dir(config_dir, target))
    agents = wanted_agents(loom, target, chosen)
    loom.init(target, agents, wanted_source(loom, target, given_source))
    # the profile is set up either way; the project only joins in when it declares what it wants
    if not Declaration.read(target) and not declare_project(loom, target):
        return
    loom.add(target, agents)


@cli.command()
@click.argument("project", required=False, type=click.Path(file_okay=False, path_type=Path))
@click.pass_obj
def remove(config_dir: Path | None, project: Path | None) -> None:
    """Unwire PROJECT, undoing what loom put there.

    PROJECT defaults to the current directory.
    """
    profile(config_dir).remove(project_dir(project))


@cli.command()
@click.argument("project", required=False, type=click.Path(file_okay=False, path_type=Path))
@click.option("--all", "everywhere", is_flag=True, help="Refresh every wired project instead of this one.")
@click.option("--for", "asked_by", metavar="NAME", help="The agent asking, as its session hook does.")
@click.pass_obj
def sync(config_dir: Path | None, project: Path | None, everywhere: bool, asked_by: str | None) -> None:
    """Refresh PROJECT from its sources.

    PROJECT defaults to the current directory.
    """
    target = None if everywhere else project_dir(project)
    profile(config_dir).sync(target, asked_by)


@cli.command()
@click.pass_obj
def status(config_dir: Path | None) -> None:
    """Show the sources and the wired projects."""
    profile(config_dir).status()


@cli.command()
@click.pass_obj
def uninstall(config_dir: Path | None) -> None:
    """Undo everything this profile installed."""
    profile(config_dir).uninstall()


if __name__ == "__main__":
    cli()
