from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import click
import questionary


def can_ask() -> bool:
    """Whether a person is at a terminal to answer."""
    return sys.stdin.isatty()


@dataclass(frozen=True)
class Choice:
    """One option of a pick."""

    name: str
    # shown in brackets after the name
    note: str = ""
    ticked: bool = False
    # why the option is shown but cannot be picked; empty when it can
    locked_because: str = ""

    @property
    def label(self) -> str:
        if not self.note:
            return self.name
        return f"{self.name}  ({self.note})"


def ask(question: str, default: str = "", check: Callable[[str], bool | str] | None = None) -> str:
    """A typed answer, with the line editing a terminal is expected to have."""

    def accepting_the_default(value: str) -> bool | str:
        # an empty answer is how the suggestion is taken, so it must pass whatever the answer itself has to
        if default and not value.strip():
            return True
        if check is None:
            return True
        return check(value)

    # shown rather than pre-filled: a filled buffer turns typing into appending to the suggestion
    shown = f"{question} [{default}]:" if default else f"{question}:"
    return _answered(questionary.text(shown, validate=accepting_the_default)).strip() or default


def pick(question: str, choices: list[Choice], *, required: bool = False) -> tuple[str, ...]:
    """The names of the choices ticked with <space>."""
    # nothing to choose from is not worth a question
    if not choices:
        return ()
    options = [
        questionary.Choice(
            choice.label, value=choice.name, checked=choice.ticked, disabled=choice.locked_because or None
        )
        for choice in choices
    ]
    if required:
        prompt = questionary.checkbox(
            question,
            choices=options,
            validate=lambda picked: True if picked else "nothing picked — <space> selects, <enter> confirms",
        )
    else:
        prompt = questionary.checkbox(question, choices=options)
    return tuple(_answered(prompt))


def confirm(question: str) -> bool:
    # enter confirms, so a mistyped key can still be taken back
    return _answered(questionary.confirm(question, default=True, auto_enter=False))


def _answered(prompt: questionary.Question) -> Any:  # noqa: ANN401 — questionary types no answer
    """The answer, or an abort when the person pressed Ctrl-C."""
    answer = prompt.ask()
    if answer is None:
        raise click.Abort
    return answer
