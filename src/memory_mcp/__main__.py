import sys

from memory_mcp.server import mcp
from memory_mcp.storage import get_root, init_memory_dir


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "init":
        result = init_memory_dir(get_root())
        print(f"Memory directory: {result['root']}")
        if result["created_directories"]:
            print(f"Created: {', '.join(result['created_directories'])}")
        if result["seeded_files"]:
            print(f"Seeded: {', '.join(result['seeded_files'])}")
        if not result["created_directories"] and not result["seeded_files"]:
            print("Already initialized — nothing to do.")
        return

    # Auto-init on server start (creates dirs/files only if missing)
    init_memory_dir(get_root())
    mcp.run()


if __name__ == "__main__":
    main()
