from __future__ import annotations

from pathlib import Path

import click

from loomwork import COMMAND_NAME, paths, prompts
from loomwork.agents import ClaudeCode
from loomwork.declaration import Declaration, DeclaredSource, Manifest
from loomwork.loom import Loom
from loomwork.output import warn
from loomwork.sources import Catalog, RepoAddress


def wanted_source(loom: Loom, project: Path, source: str | None) -> str | None:
    """Where this profile's rules come from — asked only when neither the flag, the project nor the profile says."""
    if source or Declaration.read(project) or loom.registry.sources or not prompts.can_ask():
        return source
    return _ask_source()


def wanted_agents(loom: Loom, project: Path, chosen: str | None) -> tuple[str, ...]:
    """Which agents this project is wired for — any we support, installed here or not."""
    if chosen:
        return _named_agents(chosen, tuple(agent.NAME for agent in loom.agents))
    if not prompts.can_ask():
        # nobody to ask, so a scripted run gets what this machine actually has
        return tuple(agent.NAME for agent in loom.present())
    usual = loom.usual_agents(project)
    choices = []
    for agent in loom.agents:
        note = ""
        if not agent.is_present():
            note = "not installed here"
        choices.append(prompts.Choice(agent.NAME, note=note, ticked=agent.NAME in usual))
    return prompts.pick("Wire this project for", choices, required=True)


def wanted_config_dir(given: Path | None, project: Path) -> Path:
    """Claude's config dir for the profile — asked only when neither the flag nor the default profile settles it."""
    if given:
        return given.expanduser()
    default = ClaudeCode.DEFAULT_CONFIG_DIR
    if Loom(default).registry.knows_project(project) or not prompts.can_ask():
        return default
    answer = prompts.ask("Claude config dir for this profile", default=str(default), check=valid_directory)
    return Path(answer).expanduser()


def declare_project(loom: Loom, project: Path) -> bool:
    """Ask what the project takes from a source and write its declaration; False when it stays undeclared."""
    if not prompts.can_ask():
        warn(f"{project} carries no {Declaration.FILE_NAME} — run '{COMMAND_NAME} init' from a terminal to write one")
        return False
    if not prompts.confirm(f"Declare {Declaration.FILE_NAME} in {project.name}?"):
        return False
    given = _ask_source(default=loom.most_declared_source() or "")
    catalog = Catalog.of(loom.add_source(given))
    rules = prompts.pick("Rules this project uses", _source_choices(catalog.offered_rules, catalog.global_rules))
    skills = prompts.pick("Skills this project uses", _source_choices(catalog.offered_skills, catalog.global_skills))
    loom.declare(project, (DeclaredSource(source=given, rules=rules, skills=skills),))
    if loom.unignored(project) and prompts.confirm("Update .gitignore?"):
        loom.ignore_what_we_write(project)
    return True


def valid_source(value: str) -> bool | str:
    """A directory on this machine, or something that parses as a repo we could clone."""
    given = value.strip()
    if not given:
        return "a checkout path, or <host>/<owner>/<repo>"
    local = paths.as_path(given)
    if local is not None:
        if not local.is_dir():
            return "no such directory"
        return True
    try:
        RepoAddress.from_spelling(given)
    except ValueError as unparsable:
        return str(unparsable)
    return True


def valid_directory(value: str) -> bool | str:
    """Claude's config dir — it need not exist yet, but it has to be a path."""
    given = value.strip()
    if not given:
        return "a directory path, such as ~/.claude-work"
    if not Path(given).expanduser().is_absolute():
        return "an absolute path, or one starting with ~"
    return True


def _named_agents(chosen: str, supported: tuple[str, ...]) -> tuple[str, ...]:
    """The agents a --agents value names, refused when one of them is not supported."""
    named = tuple(name.strip() for name in chosen.split(",") if name.strip())
    unknown = [name for name in named if name not in supported]
    if unknown:
        raise click.BadParameter(f"unsupported: {', '.join(unknown)}. Supported: {', '.join(supported)}")
    return named


def _source_choices(offered: tuple[str, ...], handed_out: tuple[str, ...]) -> list[prompts.Choice]:
    """What a source offers, then what it hands out anyway — shown, but no choice."""
    locked_because = f"marked global in the source's {Manifest.FILE_NAME}"
    return [
        *(prompts.Choice(name) for name in offered),
        *(prompts.Choice(name, locked_because=locked_because) for name in handed_out),
    ]


def _ask_source(default: str = "") -> str:
    return prompts.ask(
        "Where the rules come from (a checkout, or <host>/<owner>/<repo>)", default=default, check=valid_source
    )
