from enum import Enum
from typing import NoReturn

import click

from loomwork import COMMAND_NAME

# dimmed, so the coloured word after it is what the eye lands on
_PREFIX = click.style(f"{COMMAND_NAME}:", dim=True)


def info(message: str) -> None:
    """A step and, on indented lines, its detail."""
    _Level.INFO.echo(message)


def warn(message: str) -> None:
    _Level.WARNING.echo(message)


def error(message: str) -> NoReturn:
    """Say what stopped the run, and exit 1."""
    _Level.ERROR.echo(message)
    raise SystemExit(1)


class _Level(Enum):
    """What a line is, valued by the colour its first word gets."""

    INFO = "green"
    WARNING = "yellow"
    ERROR = "red"

    def echo(self, message: str) -> None:
        click.echo(self._styled(message), err=self.to_stderr)

    def _styled(self, message: str) -> str:
        """Each line behind our prefix, its first word in the level's colour — the verb of a step, the name of the others."""
        return "\n".join(f"{_PREFIX} {self._styled_line(line)}" for line in message.splitlines())

    def _styled_line(self, line: str) -> str:
        if line.startswith(" "):
            # an indented line belongs to the one above it, and reads as detail rather than as another step
            return click.style(line, dim=True)
        first, *rest = f"{self.label}{line}".split(" ", 1)
        return " ".join([click.style(first, fg=self.value, bold=True), *rest])

    @property
    def to_stderr(self) -> bool:
        return self is not _Level.INFO

    @property
    def label(self) -> str:
        """The word a line of this level opens with, so a warning reads as one without colour."""
        if self is _Level.INFO:
            return ""
        return f"{self.name} "
