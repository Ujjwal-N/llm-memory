"""FastMCP server: instructions, tools, resources, and prompts for the memory layer."""

from fastmcp import FastMCP

INSTRUCTIONS = """\
You are connected to a personal memory layer stored as markdown files.

STARTUP: At the start of every session:
1. Read me/now.md (via memory://me/now) for the user's current focus.
2. Read me/conventions.md (via memory://me/conventions) for style and communication preferences.
3. Call scan_schema to get the full directory tree.

WORKFLOWS:
- When the user reports something they did, learned, or decided: call append_daily with \
a topic. Cross-reference related projects with [[wikilinks]].
- When the user's focus or priorities change: also update me/now.md via write_file.
- Before writing any file: read it first to preserve existing content, merge your \
changes, then write back the complete file.
- After any structural change (creating/moving/deleting files): call scan_schema to \
refresh your map.

STRUCTURE:
- me/ pages are living documents — update in place, never append.
- daily/ logs are append-only — one file per day.
- projects/ support arbitrary nesting. Every directory has an _index.md. When a file \
grows beyond ~150 lines, suggest splitting into a subdirectory. Confirm with the user \
before restructuring.

WIKILINKS: Use [[slug]] to reference other files. [[project-slug]] for project _index, \
[[project/topic]] for nested content, [[YYYY-MM-DD]] for daily logs, [[now]] or \
[[conventions]] for me/ pages. Always add wikilinks when referencing related content.\
"""

mcp = FastMCP("memory", instructions=INSTRUCTIONS)

if __name__ == "__main__":
    mcp.run()
