import tomllib
from pathlib import Path

from loomwork.errors import LoomError


def parsed(toml_file: Path) -> dict:
    """The file's contents, refused in one line naming it — a session hook's error shows its first line only."""
    try:
        return tomllib.loads(toml_file.read_text())
    except tomllib.TOMLDecodeError as broken:
        raise LoomError("broken_toml", f"{toml_file}: {broken}") from broken
