"""File I/O operations for the memory layer: read, write, scan, move, delete."""

import json
import os
import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import TypedDict
from zoneinfo import ZoneInfo

import frontmatter

# Timezone for dates (log filenames, frontmatter timestamps)
_TZ = ZoneInfo(os.environ.get("MEMORY_TZ", "America/Los_Angeles"))

# File conventions
FILE_EXT = ".md"
INDEX_FILE = f"_index{FILE_EXT}"
MD_PATTERN = f"*{FILE_EXT}"

# Top-level directory names
DIR_ME = "me"
DIR_DAILY = "daily"
DIR_PROJECTS = "projects"

# Base frontmatter applied to ALL sections
BASE_FRONTMATTER = ("updated", "links")


class Behavior(StrEnum):
    """Section behavior types.

    - FIXED: immutable set of pages (valid_files required). No create/delete/move.
    - LOG: flat, append-only dated files. Supports delete. No move.
    - TREE: free-form file hierarchy. Supports create/delete/move.
    """

    FIXED = "fixed"
    LOG = "log"
    TREE = "tree"


@dataclass(frozen=True)
class DirConfig:
    """Configuration for a memory directory (top-level section or nested)."""

    behavior: Behavior
    description: str
    extra_frontmatter: tuple[str, ...] = ()
    valid_files: frozenset[str] | None = None  # required for fixed behavior


class PathResult(TypedDict):
    """Return type for mutation operations that confirm the affected path."""

    path: str


DEFAULT_SECTIONS: dict[str, DirConfig] = {
    DIR_ME: DirConfig(
        behavior=Behavior.FIXED,
        description="Fixed set of living documents: now, about, conventions, goals.",
        valid_files=frozenset(("now", "about", "conventions", "goals")),
    ),
    DIR_DAILY: DirConfig(
        behavior=Behavior.LOG,
        description="Append-only daily logs, one file per day.",
        extra_frontmatter=("date",),
    ),
    DIR_PROJECTS: DirConfig(
        behavior=Behavior.TREE,
        description="Free-form project hierarchy with arbitrary nesting.",
    ),
}

_bootstrap: dict[str, DirConfig] = dict(DEFAULT_SECTIONS)

# Regex for extracting wikilinks
_WIKILINK_RE = re.compile(r"\[\[([^\[\]]+)\]\]")

_VALID_BEHAVIORS: frozenset[str] = frozenset(Behavior)


# --- Section loading ---


def _parse_sections_json(raw: str) -> dict[str, DirConfig]:
    """Parse MEMORY_SECTIONS JSON into DirConfig objects.

    Expected format: {"name": {"behavior": "tree", "description": "...", ...}}
    Only behavior and description are required; other fields have defaults per behavior.
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"MEMORY_SECTIONS is not valid JSON: {e}") from e

    if not isinstance(data, dict):
        raise ValueError("MEMORY_SECTIONS must be a JSON object")

    sections: dict[str, DirConfig] = {}
    for name, cfg in data.items():
        if not isinstance(cfg, dict):
            raise ValueError(f"Section '{name}' must be a JSON object")
        if not name or not name.isidentifier():
            raise ValueError(
                f"Section name must be a valid identifier (letters, digits, underscores). Got: '{name}'"
            )
        if name in DEFAULT_SECTIONS:
            raise ValueError(
                f"Cannot override default section '{name}' via MEMORY_SECTIONS"
            )

        behavior = cfg.get("behavior")
        if behavior not in _VALID_BEHAVIORS:
            raise ValueError(
                f"Section '{name}': behavior must be one of {sorted(_VALID_BEHAVIORS)}, got '{behavior}'"
            )

        description = cfg.get("description")
        if not description:
            raise ValueError(f"Section '{name}': description is required")

        valid_files_raw = cfg.get("valid_files")
        valid_files = frozenset(valid_files_raw) if valid_files_raw else None

        if behavior == Behavior.FIXED and not valid_files:
            raise ValueError(f"Section '{name}': fixed behavior requires valid_files")
        if valid_files:
            for f in valid_files:
                if not f or "/" in f:
                    raise ValueError(
                        f"Section '{name}': valid_files entry '{f}' must be a "
                        f"simple name (no slashes or empty strings)."
                    )

        extra_fm = cfg.get("extra_frontmatter")
        if extra_fm:
            unknown = set(extra_fm) - set(_FRONTMATTER_HANDLERS)
            if unknown:
                raise ValueError(
                    f"Section '{name}': unknown extra_frontmatter fields {sorted(unknown)}. "
                    f"Registered handlers: {sorted(_FRONTMATTER_HANDLERS)}"
                )
        extra = tuple(extra_fm) if extra_fm else ()
        if behavior == Behavior.LOG and "date" not in extra:
            extra = ("date", *extra)

        sections[name] = DirConfig(
            behavior=Behavior(behavior),
            description=description,
            extra_frontmatter=extra,
            valid_files=valid_files,
        )

    return sections


def load_sections() -> dict[str, DirConfig]:
    """Load sections from DEFAULT_SECTIONS + MEMORY_SECTIONS env var.

    Returns DEFAULT_SECTIONS merged with any custom sections from the env var.
    """
    raw = os.environ.get("MEMORY_SECTIONS")
    if not raw:
        return dict(DEFAULT_SECTIONS)
    custom = _parse_sections_json(raw)
    return DEFAULT_SECTIONS | custom


def apply_sections(sections: dict[str, DirConfig]) -> None:
    """Update module-level _bootstrap dict in-place."""
    _bootstrap.clear()
    _bootstrap.update(sections)


# --- Path wrapper ---


@dataclass(frozen=True)
class MemoryPath:
    """A validated, section-prefixed path in the memory directory.

    File paths end with .md: "me/now.md", "projects/acme/notes.md"
    Directory paths end with /: "projects/", "projects/acme/"
    Anything else is rejected.

    API uses factory methods and fluent validation:
    - parse_file(path) / parse_dir(path): parse + type-check in one step (preferred)
    - parse(path): parse without type constraint (internal use)
    - ensure_file() / ensure_dir(): fluent type guards, return self for chaining
    - resolve_file(root) / resolve_dir(root): convert to absolute filesystem Path

    Direct construction MemoryPath(section, subpath) is for internal code with known-good parts.
    """

    section: str
    subpath: str
    is_dir: bool = False

    def __post_init__(self) -> None:
        if self.is_dir and self.subpath.endswith(".md"):
            raise ValueError(f"Directory path has .md subpath: {self.subpath}")
        if not self.is_dir and not self.subpath.endswith(".md"):
            raise ValueError(f"File path must have .md subpath: {self.subpath}")

    def __str__(self) -> str:
        base = f"{self.section}/{self.subpath}" if self.subpath else self.section
        return f"{base}/" if self.is_dir else base

    @staticmethod
    def _validate_section(section: str, path: str) -> None:
        """Raise if section is not in _bootstrap."""
        if section not in _bootstrap:
            raise ValueError(
                f"Path must start with a known section "
                f"({', '.join(_bootstrap)}). Got: {path!r}"
            )

    @classmethod
    def parse(cls, path: str) -> "MemoryPath":
        """Parse a path. Must end with .md (file) or / (directory)."""
        if path.endswith("/"):
            clean = path.rstrip("/")
            parts = clean.split("/", 1)
            section = parts[0]
            subpath = parts[1] if len(parts) > 1 else ""
            cls._validate_section(section, path)
            return cls(section=section, subpath=subpath, is_dir=True)

        if path.endswith(".md"):
            parts = path.split("/", 1)
            section = parts[0]
            subpath = parts[1] if len(parts) > 1 else ""
            cls._validate_section(section, path)
            if not subpath:
                raise ValueError(f"File path must include a subpath. Got: {path!r}")
            return cls(section=section, subpath=subpath, is_dir=False)

        raise ValueError(
            f"Path must end with .md (file) or / (directory). Got: {path!r}"
        )

    @classmethod
    def parse_file(cls, path: str) -> "MemoryPath":
        """Parse and validate as a file path (must end with .md)."""
        return cls.parse(path).ensure_file()

    @classmethod
    def parse_dir(cls, path: str) -> "MemoryPath":
        """Parse and validate as a directory path (must end with /)."""
        return cls.parse(path).ensure_dir()

    def ensure_file(self) -> "MemoryPath":
        """Validate this is a file path. Returns self for chaining."""
        if self.is_dir:
            raise ValueError(
                f"Expected a file path (ending in .md), got directory: {self}"
            )
        return self

    def ensure_dir(self) -> "MemoryPath":
        """Validate this is a directory path. Returns self for chaining."""
        if not self.is_dir:
            raise ValueError(
                f"Expected a directory path (trailing /), got file: {self}"
            )
        return self

    def resolve_file(self, root: Path) -> Path:
        """Resolve to an absolute file path. Rejects directory paths."""
        self.ensure_file()
        full = (root / self.section / self.subpath).resolve()
        if not full.is_relative_to(root):
            raise ValueError(f"Path escapes memory directory: {self}")
        return full

    def resolve_dir(self, root: Path) -> Path:
        """Resolve to an absolute directory path. Rejects file paths."""
        self.ensure_dir()
        full = (root / self.section / self.subpath).resolve()
        if not full.is_relative_to(root):
            raise ValueError(f"Path escapes memory directory: {self}")
        return full


# --- Frontmatter utilities ---


def _extract_wikilinks(content: str) -> list[str]:
    """Extract deduplicated, sorted [[wikilink]] slugs from markdown content."""
    return sorted(set(_WIKILINK_RE.findall(content)))


# --- Frontmatter handler registry ---

type FrontmatterHandler = Callable[[frontmatter.Post, str], None]


def _stamp_updated(post: frontmatter.Post, today: str) -> None:
    post["updated"] = today


def _stamp_links(post: frontmatter.Post, _today: str) -> None:
    post["links"] = _extract_wikilinks(post.content)


def _stamp_date(post: frontmatter.Post, today: str) -> None:
    post.metadata.setdefault("date", today)


_FRONTMATTER_HANDLERS: dict[str, FrontmatterHandler] = {
    "updated": _stamp_updated,
    "links": _stamp_links,
    "date": _stamp_date,
}


def _stamp_metadata(text: str, config: DirConfig) -> str:
    """Apply frontmatter fields from BASE_FRONTMATTER + config's extra_frontmatter.

    Each field is resolved via _FRONTMATTER_HANDLERS registry.
    """
    post = frontmatter.loads(text)
    today = datetime.now(tz=_TZ).strftime("%Y-%m-%d")

    for field in BASE_FRONTMATTER + config.extra_frontmatter:
        _FRONTMATTER_HANDLERS[field](post, today)

    return frontmatter.dumps(post)


# --- Directory config I/O ---


def read_dir_config(index_path: Path) -> DirConfig | None:
    """Read DirConfig from an _index.md file's frontmatter.

    Returns None if the file doesn't exist or has no 'behavior' field.
    Only returns a DirConfig when behavior is explicitly declared.
    """
    if not index_path.is_file():
        return None
    post = frontmatter.loads(index_path.read_text())
    behavior_raw = post.metadata.get("behavior")
    if behavior_raw not in _VALID_BEHAVIORS:
        return None
    description = str(post.metadata.get("description", ""))
    extra_fm_raw = post.metadata.get("extra_frontmatter")
    extra_fm = tuple(extra_fm_raw) if isinstance(extra_fm_raw, list) else ()
    valid_files_raw = post.metadata.get("valid_files")
    valid_files = (
        frozenset(valid_files_raw) if isinstance(valid_files_raw, list) else None
    )
    return DirConfig(
        behavior=Behavior(str(behavior_raw)),
        description=description,
        extra_frontmatter=extra_fm,
        valid_files=valid_files,
    )


def write_dir_config(index_path: Path, config: DirConfig, content: str) -> None:
    """Write _index.md with DirConfig fields in frontmatter.

    Stamps config fields (behavior, description, etc.) into frontmatter
    and writes the provided content as the markdown body.
    """
    post = frontmatter.loads(content)
    post["behavior"] = str(config.behavior)
    post["description"] = config.description
    if config.extra_frontmatter:
        post["extra_frontmatter"] = list(config.extra_frontmatter)
    if config.valid_files:
        post["valid_files"] = sorted(config.valid_files)
    index_path.write_text(frontmatter.dumps(post))


# --- Core path utilities ---


DEFAULT_MEMORY_DIR = Path.cwd() / "memory"


def get_root() -> Path:
    """Resolve the memory directory root from MEMORY_DIR env var or ./memory in the current working directory."""
    return Path(os.environ.get("MEMORY_DIR", DEFAULT_MEMORY_DIR)).expanduser().resolve()


# --- Init ---


def _seed_file(path: Path, title: str, config: DirConfig) -> None:
    """Write a starter markdown file with a heading and stamped frontmatter."""
    content = _stamp_metadata(f"# {title}\n", config)
    path.write_text(content)


def init_memory_dir(root: Path) -> dict:
    """Create the base memory directory structure if it doesn't exist.

    Creates directories for all configured sections and seeds fixed sections with starter pages.
    Safe to run repeatedly — only creates what's missing.
    Raises SystemExit with a clear message if the root path is invalid.
    """
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise SystemExit(f"Cannot create memory directory at {root}: {e}") from e

    if not root.is_dir():
        raise SystemExit(f"Memory path exists but is not a directory: {root}")

    created: list[str] = []

    for d in _bootstrap:
        target = root / d
        if not target.exists():
            target.mkdir(parents=True)
            created.append(d)

    created_files: list[str] = []
    for section, config in _bootstrap.items():
        if config.behavior == Behavior.FIXED and not config.valid_files:
            raise SystemExit(
                f"Section '{section}' has fixed behavior but no valid_files."
            )
        if config.behavior == Behavior.FIXED and config.valid_files:
            for page in sorted(config.valid_files):
                mp = MemoryPath(section, f"{page}.md")
                target = mp.resolve_file(root)
                if not target.exists():
                    _seed_file(target, page.title(), config)
                    created_files.append(str(mp))

    return {
        "root": str(root),
        "created_directories": created,
        "seeded_files": created_files,
    }


# --- Read ---


def read_file(root: Path, path: str) -> str:
    """Read a markdown file by its full path (e.g. "me/now.md")."""
    mp = MemoryPath.parse_file(path)
    target = mp.resolve_file(root)

    if not target.is_file():
        raise ValueError(f"File not found: {mp}")
    return target.read_text()


# --- Scan ---


def _file_modified(path: Path) -> str:
    """Return last-modified UTC timestamp for a file."""
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )


def _scan_tree(directory: Path, section: str, rel_path: str = "") -> list[dict]:
    """Recursively build a tree of files and subdirectories.

    section is the top-level section name (e.g. "projects").
    rel_path is the path within the section (e.g. "acme/v2"), empty for section root.
    """
    entries: list[dict] = []
    for child in sorted(directory.iterdir()):
        if child.name.startswith("."):
            continue
        child_rel = f"{rel_path}/{child.name}" if rel_path else child.name
        if child.is_dir():
            mp = MemoryPath(section, child_rel, is_dir=True)
            entries.append(
                {
                    "path": str(mp),
                    "children": _scan_tree(child, section, child_rel),
                }
            )
        elif child.suffix == FILE_EXT:
            mp = MemoryPath(section, child_rel)
            entries.append(
                {
                    "path": str(mp),
                    "modified": _file_modified(child),
                }
            )
    return entries


def _scan_fixed(directory: Path, section: str) -> list[dict]:
    """Scan a fixed-behavior section: flat file list."""
    if not directory.is_dir():
        return []
    return [
        {
            "path": str(MemoryPath(section, f.name)),
            "modified": _file_modified(f),
        }
        for f in sorted(directory.glob(MD_PATTERN))
    ]


def _scan_log(directory: Path, section: str, limit: int = 20) -> list[dict]:
    """Scan a log-behavior section: most recent N files, reverse sorted."""
    if not directory.is_dir():
        return []
    return [
        {
            "path": str(MemoryPath(section, f.name)),
            "modified": _file_modified(f),
        }
        for f in sorted(directory.glob(MD_PATTERN), reverse=True)[:limit]
    ]


def _scan_section(directory: Path, section: str, config: DirConfig) -> list[dict]:
    """Dispatch to the appropriate scanner based on section behavior."""
    if not directory.is_dir():
        return []
    if config.behavior == Behavior.FIXED:
        return _scan_fixed(directory, section)
    if config.behavior == Behavior.LOG:
        return _scan_log(directory, section)
    return _scan_tree(directory, section)


def scan_schema(root: Path, path: str | None = None) -> dict:
    """Walk the memory directory and return a structured schema.

    File entries: {path (ends with .md), modified}.
    Directory entries: {path (ends with /), children}.
    Path suffixes are self-describing: .md = file, / = directory.
    If path is given (must end with /), scans only that directory.
    """
    if path is None:
        result: dict = {}
        for section, config in _bootstrap.items():
            key = str(MemoryPath(section, "", is_dir=True))
            result[key] = _scan_section(root / section, section, config)
        return result

    mp = MemoryPath.parse_dir(path)
    target = mp.resolve_dir(root)
    config = _bootstrap[mp.section]

    if not mp.subpath:
        return {
            "path": str(mp),
            "entries": _scan_section(target, mp.section, config),
        }

    if not target.is_dir():
        raise ValueError(f"Not a directory: {mp}")
    return {"path": str(mp), "tree": _scan_tree(target, mp.section, mp.subpath)}


def _check_behavior(section: str, expected: Behavior) -> DirConfig:
    """Assert section has the expected behavior and return its config.

    Raises RuntimeError on mismatch (indicates a routing bug in the server layer).
    """
    config = _bootstrap.get(section)
    if config is None or config.behavior != expected:
        actual = config.behavior if config else "unknown"
        raise RuntimeError(
            f"Internal error: '{section}' has behavior '{actual}', "
            f"expected {expected}. This is a bug in tool routing."
        )
    return config


# --- FIXED section (generic) ---


def update_fixed_page(root: Path, path: str, content: str) -> PathResult:
    """Update a page in a fixed-behavior section. Auto-stamps frontmatter."""
    mp = MemoryPath.parse_file(path)
    config = _check_behavior(mp.section, Behavior.FIXED)
    stem = mp.subpath.removesuffix(".md")
    if config.valid_files and stem not in config.valid_files:
        valid = ", ".join(
            str(MemoryPath(mp.section, f"{f}.md")) for f in sorted(config.valid_files)
        )
        raise ValueError(f"Invalid page '{mp}'. Valid pages: {valid}.")

    content = _stamp_metadata(content, config)
    target = mp.resolve_file(root)
    target.write_text(content)
    return {"path": str(mp)}


# --- LOG section (generic) ---


def add_log_entry(root: Path, section: str, content: str) -> PathResult:
    """Append an entry to today's log in the given section."""
    config = _check_behavior(section, Behavior.LOG)
    date_str = datetime.now(tz=_TZ).strftime("%Y-%m-%d")
    mp = MemoryPath(section, f"{date_str}.md")
    target = mp.resolve_file(root)

    if not target.exists():
        _seed_file(target, date_str, config)

    with target.open("a") as f:
        f.write(content)

    full_text = target.read_text()
    full_text = _stamp_metadata(full_text, config)
    target.write_text(full_text)

    return {"path": str(mp)}


def edit_log(root: Path, path: str, content: str) -> PathResult:
    """Create or overwrite a log entry by full path. Use for corrections and backfilling."""
    mp = MemoryPath.parse_file(path)
    config = _check_behavior(mp.section, Behavior.LOG)
    target = mp.resolve_file(root)
    content = _stamp_metadata(content, config)
    target.write_text(content)
    return {"path": str(mp)}


# --- TREE section (generic) ---


def _check_parent_exists(parent: Path, section: str, root: Path) -> None:
    """Raise if a parent directory doesn't exist."""
    if not parent.exists():
        parent_rel = str(parent.relative_to(root / section))
        mp = MemoryPath(section, parent_rel, is_dir=True)
        raise ValueError(
            f"Directory does not exist: {mp}. Use create_directory to create it first."
        )


def create_directory(root: Path, path: str) -> PathResult:
    """Create a directory in a tree-behavior section.

    Only creates one level — parent must already exist.
    """
    mp = MemoryPath.parse_dir(path)
    _check_behavior(mp.section, Behavior.TREE)
    target = mp.resolve_dir(root)

    if target.exists():
        raise ValueError(f"Directory already exists: {mp}")

    _check_parent_exists(target.parent, mp.section, root)
    target.mkdir()
    return {"path": str(mp)}


def write_tree_file(root: Path, path: str, content: str) -> PathResult:
    """Create or overwrite a file in a tree-behavior section.

    Parent directory must already exist — use create_directory first.
    """
    mp = MemoryPath.parse_file(path)
    config = _check_behavior(mp.section, Behavior.TREE)
    target = mp.resolve_file(root)

    _check_parent_exists(target.parent, mp.section, root)

    content = _stamp_metadata(content, config)
    target.write_text(content)
    return {"path": str(mp)}


def move_tree_file(root: Path, source: str, destination: str) -> PathResult:
    """Move or rename a file within a tree-behavior section."""
    src_mp = MemoryPath.parse_file(source)
    _check_behavior(src_mp.section, Behavior.TREE)
    dst_mp = MemoryPath.parse_file(destination)
    if _bootstrap[dst_mp.section].behavior != Behavior.TREE:
        raise ValueError(
            f"Cannot move files into '{dst_mp.section}/' — only tree sections support moves."
        )
    src = src_mp.resolve_file(root)
    dst = dst_mp.resolve_file(root)

    if not src.is_file():
        raise ValueError(
            f"Source not found: {src_mp}. Use scan_schema to find valid paths."
        )
    if dst.is_file():
        raise ValueError(f"Destination already exists: {dst_mp}")

    _check_parent_exists(dst.parent, dst_mp.section, root)
    shutil.move(str(src), str(dst))
    return {"path": str(dst_mp)}


def delete_file(root: Path, path: str) -> PathResult:
    """Delete a file in any non-fixed section.

    Refuses to delete _index.md if the directory still contains other files.
    Cleans up empty parent directories after deletion.
    """
    mp = MemoryPath.parse_file(path)
    if _bootstrap[mp.section].behavior == Behavior.FIXED:
        raise ValueError(f"Cannot delete files in '{mp.section}/' (fixed section).")
    target = mp.resolve_file(root)

    if not target.is_file():
        raise ValueError(f"File not found: {mp}. Use scan_schema to find valid paths.")

    if target.name == INDEX_FILE:
        siblings = [p for p in target.parent.iterdir() if p != target]
        if siblings:
            raise ValueError(
                "Cannot delete _index.md while directory contains other files. "
                "Delete or move those first."
            )

    target.unlink()

    section_dir = root / mp.section
    parent = target.parent
    while parent != section_dir and not any(parent.iterdir()):
        parent.rmdir()
        parent = parent.parent

    return {"path": str(mp)}
