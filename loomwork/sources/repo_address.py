from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from loomwork import git, paths

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class RepoAddress:
    """Where a rules repo lives on its host, however its url was written."""

    host: str
    owner: str
    repo: str
    # the folder in the repo that holds the rules, when they are not at its root
    subdirectory: str = ""

    @classmethod
    def parse(cls, location: str) -> RepoAddress:
        """Read <host>/<owner>/<repo>[/<subdirectory>] out of any form of the url — bare, https, scp-style or ssh://."""
        url = location.strip().rstrip("/")
        if "://" not in url:
            # scp-style (git@host:owner/repo) and bare (host/owner/repo) both read as scheme-less urls
            url = "//" + url.replace(":", "/", 1)
        parsed = urlsplit(url)
        parts = [part for part in parsed.path.split("/") if part]
        owner, repo, *subdirectory = [*parts, "", ""]
        host = parsed.hostname or ""
        # .git ends the repo segment even when a pasted clone url has a subdirectory after it
        repo = repo.removesuffix(".git")
        if not host or not repo:
            raise ValueError(f"'{location}' is no <host>/<owner>/<repo> — cannot tell where to clone it from")
        return cls(host, owner, repo, "/".join(part for part in subdirectory if part))

    @classmethod
    def of_checkout(cls, checkout: Path) -> RepoAddress | None:
        """The repo a checkout was cloned from, down to the folder inside it — None when it has no origin."""
        remote = git.origin(checkout)
        if remote is None:
            return None
        inside = checkout.relative_to(git.root(checkout))
        subdirectory = ""
        if str(inside) != ".":
            subdirectory = str(inside)
        return replace(cls.parse(remote), subdirectory=subdirectory)

    @property
    def key(self) -> str:
        """The same however this repo's url is written: what loom files it under."""
        return "/".join(part for part in (self.host, self.owner, self.repo, self.subdirectory) if part)

    @property
    def clone_dir(self) -> Path:
        return paths.SOURCES_DIR / self.host / self.owner / self.repo
