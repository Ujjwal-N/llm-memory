"""Shared fixtures for memory-mcp tests."""

from pathlib import Path

import pytest

from memory_mcp import storage


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    """Create and initialize a fresh memory directory, restoring _bootstrap after."""
    saved = dict(storage._bootstrap)
    storage.apply_sections(dict(storage.DEFAULT_SECTIONS))
    storage.init_memory_dir(tmp_path)
    yield tmp_path
    storage._bootstrap.clear()
    storage._bootstrap.update(saved)
