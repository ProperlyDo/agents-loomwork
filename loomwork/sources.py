from __future__ import annotations

import shutil
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import urlsplit

from loomwork import COMMAND_NAME, git, paths
from loomwork.declaration import Manifest
from loomwork.output import error, info, warn


@dataclass(frozen=True)
class RepoAddress:
    """Where a rules repo lives on its host, however its url was spelled."""

    host: str
    owner: str
    repo: str
    # the folder in the repo that holds the rules, when they are not at its root
    subdirectory: str = ""

    @classmethod
    def from_spelling(cls, spelling: str) -> RepoAddress:
        """Read <host>/<owner>/<repo>[/<subdirectory>] out of any spelling — bare, https, scp-style or ssh://."""
        url = spelling.strip().rstrip("/")
        if "://" not in url:
            # scp-style (git@host:owner/repo) and bare (host/owner/repo) both read as scheme-less urls
            url = "//" + url.replace(":", "/", 1)
        parsed = urlsplit(url)
        parts = [part for part in parsed.path.split("/") if part]
        owner, repo, *subdirectory = [*parts, "", ""]
        host = parsed.hostname or ""
        # .git belongs to the repo segment, and a subdirectory may follow it in a pasted clone url
        repo = repo.removesuffix(".git")
        if not host or not repo:
            raise ValueError(f"'{spelling}' is no <host>/<owner>/<repo> — cannot tell where to clone it from")
        return cls(host, owner, repo, "/".join(part for part in subdirectory if part))

    @property
    def key(self) -> str:
        """The same for every spelling of this repo: what a profile files it under."""
        return "/".join(part for part in (self.host, self.owner, self.repo, self.subdirectory) if part)

    @property
    def clone_urls(self) -> tuple[str, ...]:
        # ssh first, since a team's rules are usually private
        return (
            f"git@{self.host}:{self.owner}/{self.repo}.git",
            f"https://{self.host}/{self.owner}/{self.repo}.git",
        )

    @property
    def clone_dir(self) -> Path:
        return paths.SOURCES_DIR / self.host / self.owner / self.repo


@dataclass(frozen=True)
class Catalog:
    """What a set of sources defines, merged in order — a later source wins a name two of them define."""

    # rule name → its file
    rules: dict[str, Path]
    # skill name → its folder
    skills: dict[str, Path]
    # the names a source's loom.toml hands every project, among those defined
    global_rules: tuple[str, ...]
    global_skills: tuple[str, ...]
    # the universal layer, from the last source that carries one
    agents_md: Path | None

    @classmethod
    def of(cls, *checkouts: Path) -> Catalog:
        rules: dict[str, Path] = {}
        skills: dict[str, Path] = {}
        marked_global_rules: set[str] = set()
        marked_global_skills: set[str] = set()
        agents_md = None
        for checkout in checkouts:
            rules |= {rule.stem: rule for rule in (checkout / "rules").glob("*.md")}
            skill_files = (checkout / "skills").glob("*/SKILL.md")
            skills |= {skill_file.parent.name: skill_file.parent for skill_file in skill_files}
            manifest = Manifest.read(checkout)
            marked_global_rules |= set(manifest.global_rules)
            marked_global_skills |= set(manifest.global_skills)
            # a repo without a loom.toml keeps its AGENTS.md for its own contributors
            if (checkout / Manifest.FILE_NAME).is_file() and (checkout / "AGENTS.md").is_file():
                agents_md = checkout / "AGENTS.md"
        return cls(
            rules=dict(sorted(rules.items())),
            skills=dict(sorted(skills.items())),
            global_rules=tuple(name for name in sorted(rules) if name in marked_global_rules),
            global_skills=tuple(name for name in sorted(skills) if name in marked_global_skills),
            agents_md=agents_md,
        )

    @property
    def offered_rules(self) -> tuple[str, ...]:
        """The rules a project chooses from: every one not handed out anyway."""
        return tuple(name for name in self.rules if name not in self.global_rules)

    @property
    def offered_skills(self) -> tuple[str, ...]:
        return tuple(name for name in self.skills if name not in self.global_skills)

    def rule_files(self, names: tuple[str, ...]) -> dict[str, Path]:
        """The files of the named rules, leaving out names no source defines."""
        return {name: self.rules[name] for name in names if name in self.rules}

    def skill_folders(self, names: tuple[str, ...]) -> dict[str, Path]:
        """The folders of the named skills, leaving out names no source defines."""
        return {name: self.skills[name] for name in names if name in self.skills}


def fetch(source: str) -> Path:
    """The source's directory on this machine — the path it names, or an up-to-date clone of the repo it names."""
    local = paths.as_path(source)
    if local is not None:
        if not local.is_dir():
            error(f"{source}: no such directory")
        checkout = local.resolve()
    else:
        try:
            address = RepoAddress.from_spelling(source)
        except ValueError as unparsable:
            error(str(unparsable))
        if not address.clone_dir.is_dir():
            _clone(address)
        elif not update(address.clone_dir):
            warn(f"could not update {address.key} — using the clone as it stands")
        checkout = address.clone_dir / address.subdirectory
        if not checkout.is_dir():
            error(f"{source} names {address.subdirectory}/, which the clone does not have — is it pushed?")
    if not is_source(checkout):
        error(f"{checkout} holds no rules/ or skills/ — is that a source?")
    return checkout


def update(checkout: Path) -> bool:
    """Bring a source's repo up to date, reporting whether it worked."""
    # a clone of ours holds no work, so it takes whatever the remote has; a checkout of yours only fast-forwards
    if checkout.is_relative_to(paths.SOURCES_DIR):
        return git.match_remote(checkout)
    return git.pull(checkout)


def identity(source: str) -> str:
    """The key a profile files a source under — one for every spelling of a repo, a checkout of it included."""
    local = paths.as_path(source)
    if local is not None:
        checkout = local.resolve()
        # a path with no repo behind it is only ever itself
        if not checkout.is_dir():
            return str(checkout)
        address = checkout_address(checkout)
        if address is None:
            return str(checkout)
        return address.key
    try:
        return RepoAddress.from_spelling(source).key
    except ValueError:
        return source.strip().rstrip("/")


def checkout_address(checkout: Path) -> RepoAddress | None:
    """The repo a checkout was cloned from, down to the folder inside it — None when it has no origin."""
    remote = git.origin(checkout)
    if remote is None:
        return None
    inside = checkout.relative_to(git.root(checkout))
    subdirectory = ""
    if str(inside) != ".":
        subdirectory = str(inside)
    return replace(RepoAddress.from_spelling(remote), subdirectory=subdirectory)


def is_source(path: Path) -> bool:
    """What makes a directory a source: rules, skills, or both. A universal AGENTS.md beside them is optional."""
    return (path / "rules").is_dir() or (path / "skills").is_dir()


def _clone(address: RepoAddress) -> None:
    """Clone the repo into its place, trying each url in turn."""
    # moved into place only once whole, so a clone cut off halfway is never taken for a finished one
    unfinished = address.clone_dir.with_name(f"{address.clone_dir.name}.unfinished")
    for url in address.clone_urls:
        info(f"fetching {url}")
        shutil.rmtree(unfinished, ignore_errors=True)
        if git.clone(url, unfinished):
            unfinished.rename(address.clone_dir)
            return
    shutil.rmtree(unfinished, ignore_errors=True)
    error(f"could not clone {address.key} — clone it yourself and run '{COMMAND_NAME} init --source <path>'")
