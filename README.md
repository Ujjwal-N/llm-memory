# memory-mcp

A personal memory layer for LLMs, built as an [MCP](https://modelcontextprotocol.io) server over plain markdown files.

Replaces proprietary memory systems (Claude memories, ChatGPT memory) with an open, local-first system you control and can plug into any LLM via MCP.

## Philosophy

- **You own your data.** Memory is plain markdown files on your filesystem. No database, no cloud, no vendor lock-in. Back up with git, edit with any text editor, migrate to anything.
- **The LLM owns the content.** The server manages file operations and metadata. The LLM decides what to write, how to structure it, and when to update it. Storage is format-agnostic.
- **Config-driven, not code-driven.** Section behaviors (fixed pages, append-only logs, free-form trees) are declared as config, not hardcoded per section. Add custom sections via a single env var.
- **Guardrails, not handholding.** Tools enforce structural invariants (path containment, behavior constraints, no auto-dir creation) but don't restrict content. The LLM learns section rules on demand via `describe_section`.
- **Composable paths.** Every path returned by any tool can be passed directly to any other tool. No transformation, no prefix manipulation. Unix philosophy.

## Setup

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
# Clone and install
git clone git@github.com:Ujjwal-N/llm-memory.git
cd llm-memory
uv sync

# Initialize the memory directory
uv run python -m memory_mcp init
```

### Claude Desktop / Claude Code

Add to your MCP config:

```json
{
  "mcpServers": {
    "memory": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/llm-memory", "python", "-m", "memory_mcp"],
      "env": {
        "MEMORY_DIR": "/path/to/your/memory"
      }
    }
  }
}
```

## How it works

### Sections

Memory is organized into **sections**, each with a behavior:

| Section | Behavior | Description |
|---------|----------|-------------|
| `me/` | **fixed** | Living documents: `now`, `about`, `conventions`, `goals`. Cannot create or delete. |
| `daily/` | **log** | One file per day, append-only. Auto-named by date. |
| `projects/` | **tree** | Free-form hierarchy. Create directories and files explicitly. |

### Tools (9)

| Tool | Purpose |
|------|---------|
| `describe_section` | Get section rules and applicable tools before writing |
| `scan_schema` | Map the full directory structure or a specific section |
| `read_file` | Read any file by path |
| `write_file` | Create or overwrite files (fixed and tree sections) |
| `create_directory` | Create a directory one level at a time (tree only) |
| `move_file` | Move or rename files (tree only) |
| `delete_file` | Delete files (tree and log sections) |
| `add_log_entry` | Append to today's log (log sections) |
| `edit_log` | Overwrite a log entry for corrections (log sections) |

### Paths

All paths use `section/subpath` format everywhere:

```
me/now
daily/2026-03-18
projects/acme/v1/features
```

A path from one tool's output can be passed directly to another tool.

## Configuration

| Env var | Default | Description |
|---------|---------|-------------|
| `MEMORY_DIR` | `./memory` | Path to the memory directory |
| `MEMORY_TZ` | `America/Los_Angeles` | Timezone for dates (log filenames, frontmatter) |
| `MEMORY_SECTIONS` | — | JSON to add custom sections (see below) |

### Custom sections

```bash
export MEMORY_SECTIONS='{
  "work": {
    "behavior": "tree",
    "description": "Work project notes and documentation."
  },
  "journal": {
    "behavior": "log",
    "description": "Personal journal entries, one per day."
  }
}'
```

Custom sections support the same three behaviors: `fixed`, `log`, `tree`.

## License

MIT
