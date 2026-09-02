#!/usr/bin/env bash
# curl-able entry: piped it clones to $AGENTS_CONFIG_HOME first, then hands over to install.py either way.
set -euo pipefail

# BASH_SOURCE is empty when bash reads the script from a pipe — that run has no clone yet
if [[ -n "${BASH_SOURCE[0]:-}" ]]; then
  clone_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
else
  clone_dir="${AGENTS_CONFIG_HOME:-$HOME/.agents-config}"
  if [[ ! -d "$clone_dir/.git" ]]; then
    git clone --quiet "${AGENTS_CONFIG_REPO:-git@github.com:ProperlyDo/agents-config.git}" "$clone_dir"
  fi
fi

exec "$clone_dir/install.py" install "$@"
