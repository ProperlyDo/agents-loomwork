from enum import Enum
from typing import NoReturn

import click

from loomwork import COMMAND_NAME

# dimmed, so the coloured word after it is what the eye lands on
_PREFIX = click.style(f"{COMMAND_NAME}:", dim=True)


def info(message: str) -> None:
    """A step and, on indented lines, its detail."""
    _print(_Level.INFO, message)


def warn(message: str) -> None:
    _print(_Level.WARNING, message)


def error(message: str) -> NoReturn:
    """Say what stopped the run, and exit 1."""
    _print(_Level.ERROR, message)
    raise SystemExit(1)


class _Level(Enum):
    """What a line is, valued by the colour its first word gets."""

    INFO = "green"
    WARNING = "yellow"
    ERROR = "red"


def _print(level: _Level, message: str) -> None:
    click.echo(_styled(level, message), err=level is not _Level.INFO)


def _styled(level: _Level, message: str) -> str:
    """Each line behind our prefix, its first word in the level's colour — the verb of a step, the name of the others."""
    return "\n".join(f"{_PREFIX} {_styled_line(level, line)}" for line in message.splitlines())


def _styled_line(level: _Level, line: str) -> str:
    if line.startswith(" "):
        # an indented line belongs to the one above it, and reads as detail rather than as another step
        return click.style(line, dim=True)
    if level is not _Level.INFO:
        line = f"{level.name} {line}"
    first, *rest = line.split(" ", 1)
    return " ".join([click.style(first, fg=level.value, bold=True), *rest])
