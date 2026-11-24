from loomwork import paths
from loomwork.agents import SUPPORTED_AGENTS
from loomwork.errors import LoomError
from loomwork.sources.repo_address import RepoAddress


def validate_source(location: str) -> None:
    """A directory on this machine, or something that parses as a repo we could clone."""
    source = location.strip()
    if not source:
        raise LoomError("source_missing", "a checkout path, or <host>/<owner>/<repo>")
    local = paths.as_path(source)
    if local is not None:
        if not local.is_dir():
            raise LoomError("no_such_directory", f"{source}: no such directory")
        return
    try:
        RepoAddress.parse(source)
    except ValueError as unparsable:
        raise LoomError("not_a_repo_address", str(unparsable)) from unparsable


def validate_agent_names(names: tuple[str, ...]) -> None:
    """Names of agents loom supports, installed here or not."""
    supported = tuple(kind.NAME for kind in SUPPORTED_AGENTS)
    unknown = [name for name in names if name not in supported]
    if unknown:
        raise LoomError("unsupported_agent", f"unsupported: {', '.join(unknown)}. Supported: {', '.join(supported)}")
