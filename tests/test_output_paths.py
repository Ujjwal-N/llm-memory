"""Tests ensuring all tool outputs use strict path conventions.

Every path in tool output must end with .md (file) or / (directory).
No bare section names, no ambiguous paths.
"""

from pathlib import Path

from memory_mcp import storage

# Matches any string that looks like a path: starts with a known section name
# but doesn't end with .md or /
_SECTION_NAMES = set(storage.DEFAULT_SECTIONS.keys())


def _find_bad_paths(obj: object, context: str = "") -> list[str]:
    """Recursively find path-like strings that violate .md / / conventions."""
    violations: list[str] = []
    if isinstance(obj, str):
        # A string that starts with a section name but has no .md or / suffix
        first_segment = obj.split("/")[0]
        if first_segment in _SECTION_NAMES and not obj.endswith((".md", "/")):
            violations.append(f"{context}: {obj!r}")
    elif isinstance(obj, dict):
        for k, v in obj.items():
            # dict keys that are bare section names
            if isinstance(k, str) and k in _SECTION_NAMES and not k.endswith("/"):
                violations.append(f"{context}[key]: {k!r}")
            _ctx = f"{context}.{k}" if context else str(k)
            violations.extend(_find_bad_paths(v, _ctx))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            violations.extend(_find_bad_paths(v, f"{context}[{i}]"))
    return violations


class TestScanSchemaOutput:
    def test_full_scan_keys_end_with_slash(self, root: Path) -> None:
        result = storage.scan_schema(root)
        for key in result:
            assert key.endswith("/"), f"Section key should end with /: {key!r}"

    def test_full_scan_file_paths_end_with_md(self, root: Path) -> None:
        result = storage.scan_schema(root)
        for section_entries in result.values():
            for entry in section_entries:
                if "children" not in entry:
                    assert entry["path"].endswith(".md"), (
                        f"File path should end with .md: {entry['path']!r}"
                    )

    def test_full_scan_dir_paths_end_with_slash(self, root: Path) -> None:
        storage.create_directory(root, "projects/acme/")
        result = storage.scan_schema(root)
        for section_entries in result.values():
            for entry in section_entries:
                if "children" in entry:
                    assert entry["path"].endswith("/"), (
                        f"Dir path should end with /: {entry['path']!r}"
                    )

    def test_scoped_scan_path_ends_with_slash(self, root: Path) -> None:
        result = storage.scan_schema(root, "me/")
        assert result["path"].endswith("/")

    def test_no_bad_paths_in_full_scan(self, root: Path) -> None:
        storage.create_directory(root, "projects/acme/")
        storage.write_tree_file(root, "projects/acme/notes.md", "# Notes")
        result = storage.scan_schema(root)
        violations = _find_bad_paths(result)
        assert violations == [], f"Bad paths found: {violations}"

    def test_no_type_field_in_output(self, root: Path) -> None:
        storage.create_directory(root, "projects/acme/")
        storage.write_tree_file(root, "projects/acme/notes.md", "# Notes")
        result = storage.scan_schema(root)
        assert "type" not in str(result), "Scan output should not contain 'type' field"


class TestMutationOutputPaths:
    def test_write_tree_file_path(self, root: Path) -> None:
        result = storage.write_tree_file(root, "projects/notes.md", "# Notes")
        assert result["path"].endswith(".md")

    def test_create_directory_path(self, root: Path) -> None:
        result = storage.create_directory(root, "projects/acme/")
        assert result["path"].endswith("/")

    def test_move_tree_file_path(self, root: Path) -> None:
        storage.write_tree_file(root, "projects/old.md", "# Old")
        result = storage.move_tree_file(root, "projects/old.md", "projects/new.md")
        assert result["path"].endswith(".md")

    def test_delete_file_path(self, root: Path) -> None:
        storage.write_tree_file(root, "projects/temp.md", "# Temp")
        result = storage.delete_file(root, "projects/temp.md")
        assert result["path"].endswith(".md")

    def test_update_fixed_page_path(self, root: Path) -> None:
        result = storage.update_fixed_page(root, "me/now.md", "# Now\nUpdated")
        assert result["path"].endswith(".md")

    def test_add_log_entry_path(self, root: Path) -> None:
        result = storage.add_log_entry(root, "daily", "content")
        assert result["path"].endswith(".md")

    def test_edit_log_path(self, root: Path) -> None:
        entry = storage.add_log_entry(root, "daily", "content")
        result = storage.edit_log(root, entry["path"], "# New")
        assert result["path"].endswith(".md")

    def test_edit_file_path(self, root: Path) -> None:
        storage.write_tree_file(root, "projects/notes.md", "# Notes\nBody")
        result = storage.edit_file(root, "projects/notes.md", "Body", "Edited")
        assert result["path"].endswith(".md")

    def test_init_memory_dir_seeded_files(self, root: Path) -> None:
        result = storage.init_memory_dir(root)
        for f in result["seeded_files"]:
            assert f.endswith(".md"), f"Seeded file should end with .md: {f!r}"
