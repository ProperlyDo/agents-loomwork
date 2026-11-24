from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from loomwork import COMMAND_NAME, git, paths
from loomwork.errors import LoomError
from loomwork.output import info, warn
from loomwork.sources.catalog import Catalog
from loomwork.sources.repo_address import RepoAddress
from loomwork.validators import validate_source

if TYPE_CHECKING:
    from pathlib import Path


class Source(ABC):
    """A rules repo as it was declared: a path on this machine, or an address to clone it from."""

    def __init__(self, location: str) -> None:
        self.location = location

    @staticmethod
    def of(location: str) -> Source:
        local = paths.as_path(location)
        if local is None:
            return RepoSource(location)
        return LocalSource(location, local)

    def fetch(self) -> Path:
        """The source's directory on this machine, refused when it holds no rules or skills."""
        validate_source(self.location)
        checkout = self._checkout()
        if not Catalog.has_rules_or_skills(checkout):
            raise LoomError("not_a_source", f"{checkout} holds no rules/ or skills/ — is that a source?")
        return checkout

    @abstractmethod
    def update(self, checkout: Path) -> bool:
        """Bring the repo the checkout sits in up to date, reporting whether it worked."""

    @property
    @abstractmethod
    def key(self) -> str:
        """The key loom files the source under — the same however the repo is written, a checkout of it included."""

    @abstractmethod
    def needs_adding(self, known: Path | None) -> bool:
        """Whether loom has to fetch the source, given where it last recorded it."""

    @abstractmethod
    def gone_warning(self, checkout: Path) -> str:
        """What to tell the user when the recorded checkout is no longer there."""

    @abstractmethod
    def _checkout(self) -> Path:
        """Where the source's files are on this machine, brought there or up to date first."""


class LocalSource(Source):
    """A source named by a path: a checkout of the user's own, used as it stands."""

    def __init__(self, location: str, path: Path) -> None:
        super().__init__(location)
        self.path = path

    def update(self, checkout: Path) -> bool:
        # a checkout of yours only fast-forwards
        return git.pull(checkout)

    @property
    def key(self) -> str:
        checkout = self.path.resolve()
        if not checkout.is_dir():
            return str(checkout)
        address = RepoAddress.of_checkout(checkout)
        # a checkout with no repo behind it is only ever itself
        if address is None:
            return str(checkout)
        return address.key

    def needs_adding(self, known: Path | None) -> bool:
        # a working copy of a repo we already cloned is what its author edits, so it replaces the clone
        return known is None or not known.is_dir() or (self.path.is_dir() and known != self.path.resolve())

    def gone_warning(self, checkout: Path) -> str:
        return f"source {checkout} is gone — point '{COMMAND_NAME} init --source' at where it lives now"

    def _checkout(self) -> Path:
        return self.path.resolve()


class RepoSource(Source):
    """A source named by its repo: cloned into loom's own dir, and kept matching the remote."""

    def update(self, checkout: Path) -> bool:
        # a clone of ours holds no work, so it takes whatever the remote has
        return git.match_remote(checkout)

    @property
    def key(self) -> str:
        try:
            return RepoAddress.parse(self.location).key
        except ValueError:
            return self.location.strip().rstrip("/")

    def needs_adding(self, known: Path | None) -> bool:
        # a clone deleted since it was added is fetched again, like a source never added
        return known is None or not known.is_dir()

    def gone_warning(self, checkout: Path) -> str:
        return (
            f"source {self.location} is gone from {checkout} — "
            f"run '{COMMAND_NAME} init --source {self.location}' to fetch it again"
        )

    def _checkout(self) -> Path:
        address = RepoAddress.parse(self.location)
        if not address.clone_dir.is_dir():
            self._clone(address)
        elif not self.update(address.clone_dir):
            warn(f"could not update {address.key} — using the clone as it stands")
        checkout = address.clone_dir / address.subdirectory
        if not checkout.is_dir():
            raise LoomError(
                "subdirectory_missing",
                f"{self.location} names {address.subdirectory}/, which the clone does not have — is it pushed?",
            )
        return checkout

    def _clone(self, address: RepoAddress) -> None:
        """Clone the repo into its place, trying each url in turn."""
        # moved into place only once whole, so a clone cut off halfway is never taken for a finished one
        unfinished = address.clone_dir.with_name(f"{address.clone_dir.name}.unfinished")
        for url in self._clone_urls(address):
            info(f"fetching {url}")
            shutil.rmtree(unfinished, ignore_errors=True)
            if git.clone(url, unfinished):
                unfinished.rename(address.clone_dir)
                return
        shutil.rmtree(unfinished, ignore_errors=True)
        raise LoomError(
            "clone_failed",
            f"could not clone {address.key} — clone it yourself and run '{COMMAND_NAME} init --source <path>'",
        )

    @staticmethod
    def _clone_urls(address: RepoAddress) -> tuple[str, ...]:
        # ssh first, since a team's rules are usually private
        return (
            f"git@{address.host}:{address.owner}/{address.repo}.git",
            f"https://{address.host}/{address.owner}/{address.repo}.git",
        )
