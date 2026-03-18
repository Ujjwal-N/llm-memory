"""File I/O operations for the memory layer: read, write, scan, search, move, delete."""

from pathlib import Path
import os


def get_root() -> Path:
    """Resolve the memory directory root from MEMORY_DIR env var or default to ~/memory."""
    return Path(os.environ.get("MEMORY_DIR", Path.home() / "memory")).expanduser()
