from __future__ import annotations

import os
import subprocess
from pathlib import Path
from subprocess import CompletedProcess

# a session's first answer waits on the hook that updates, so a slow network has to lose rather than hold it up
UPDATE_TIMEOUT_SECONDS = 8
CLONE_TIMEOUT_SECONDS = 120


def run(*arguments: str, inside: Path | None = None, timeout: float | None = None) -> CompletedProcess[str] | None:
    """One git call, or None when it failed — the user's own git, so their ssh agent and credential helpers apply."""
    located = ["-C", str(inside)] if inside else []
    # nobody is there to type a password or accept a host key, so git must fail instead of waiting for one
    unattended = {
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_SSH_COMMAND": os.environ.get("GIT_SSH_COMMAND", "ssh -o BatchMode=yes"),
    }
    try:
        ran = subprocess.run(
            ["git", *located, *arguments],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env={**os.environ, **unattended},
        )
    except subprocess.TimeoutExpired:
        # macOS ships no timeout(1), so this bound is the only one the hook gets
        return None
    return ran if ran.returncode == 0 else None


def clone(url: str, into: Path) -> bool:
    """Clone the tip alone — what loom reads, with no history to grow."""
    return bool(run("clone", "--quiet", "--depth", "1", url, str(into), timeout=CLONE_TIMEOUT_SECONDS))


def pull(path: Path) -> bool:
    """Fast-forward a checkout, reporting whether it worked."""
    return bool(run("pull", "--ff-only", "--quiet", inside=path, timeout=UPDATE_TIMEOUT_SECONDS))


def match_remote(path: Path) -> bool:
    """Make a clone exactly its remote's tip, rewritten history included, reporting whether it worked."""
    if not run("fetch", "--quiet", "--depth", "1", "origin", inside=path, timeout=UPDATE_TIMEOUT_SECONDS):
        return False
    return bool(run("reset", "--quiet", "--hard", "FETCH_HEAD", inside=path))


def origin(path: Path) -> str | None:
    """The url a checkout came from — None when it has no origin, which a local working copy may not."""
    asked = run("remote", "get-url", "origin", inside=path)
    if asked is None:
        return None
    return asked.stdout.strip().rstrip("/").removesuffix(".git")


def root(path: Path) -> Path:
    """The repo a path sits in, or the path itself when it is in none."""
    for candidate in (path, *path.parents):
        if (candidate / ".git").exists():
            return candidate
    return path
