import re
from pathlib import Path

# the package name is the tool name: one rename moves the marker and the registry file together
TOOL_NAME = __name__
# what a user types, and what a project's hook line calls; `loomwork` stays a second console script behind it
COMMAND_NAME = "loom"
# the .agents standard location, and not a knob — other tools (the skills CLI, OpenCode) look for it only there
AGENTS_DIR = Path("~/.agents").expanduser().resolve()
# a clone we fetched is data, not configuration, so it lands where XDG puts data
SOURCES_DIR = Path("~/.local/share/loomwork/sources").expanduser()
# a namespace is a path component, so keep it boring
NAMESPACE_RE = re.compile(r"[\w.-]+", re.ASCII)


def valid_namespace(value: str) -> bool:
    # all-dot names pass the pattern but walk out of our directories
    return bool(NAMESPACE_RE.fullmatch(value)) and bool(value.strip("."))
