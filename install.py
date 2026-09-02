#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

from installer.agents import AGENTS
from installer.installation import Installation


def namespace_word(value: str) -> str:
    # all-dot names pass the regex but walk out of our directories
    if not Installation.NAMESPACE_RE.fullmatch(value) or not value.strip("."):
        raise argparse.ArgumentTypeError("must be a single path-safe word")
    return value


def origin_owner() -> str:
    """The lowercased owner segment of the clone's origin — Acme/agents-config installs as acme."""
    origin_url = subprocess.run(
        ["git", "-C", str(Path(__file__).resolve().parent), "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    owner = re.split(r"[:/]+", origin_url.rstrip("/").removesuffix(".git"))[-2].lower()
    return namespace_word(owner)


def main() -> None:
    parser = argparse.ArgumentParser(prog="install.py")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("install", "sync", "link", "uninstall"):
        command = commands.add_parser(name)
        command.add_argument("--namespace", type=namespace_word)
        command.add_argument("--config-dir", default="~/.agents")
        if name != "install":
            command.add_argument("project", nargs="?", default=None)
    args = parser.parse_args()
    installation = Installation(
        config_dir=Path(args.config_dir).expanduser().resolve(),
        namespace=args.namespace or origin_owner(),
    )
    if args.command == "install":
        installation.install(AGENTS)
    elif args.command == "sync":
        installation.sync(args.project, AGENTS)
    elif args.command == "link":
        installation.report_wiring(installation.link(args.project, AGENTS))
    else:
        installation.uninstall(args.project, AGENTS)


if __name__ == "__main__":
    main()
