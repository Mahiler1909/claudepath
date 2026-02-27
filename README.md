# claudepath

[![CI](https://github.com/Mahiler1909/claudepath/actions/workflows/ci.yml/badge.svg)](https://github.com/Mahiler1909/claudepath/actions/workflows/ci.yml)
[![Coverage](https://codecov.io/gh/Mahiler1909/claudepath/branch/main/graph/badge.svg)](https://codecov.io/gh/Mahiler1909/claudepath)
[![PyPI version](https://img.shields.io/pypi/v/claudepath)](https://pypi.org/project/claudepath/)
[![Downloads](https://img.shields.io/pypi/dm/claudepath)](https://pypi.org/project/claudepath/)
[![Python versions](https://img.shields.io/pypi/pyversions/claudepath)](https://pypi.org/project/claudepath/)
[![License](https://img.shields.io/github/license/Mahiler1909/claudepath)](LICENSE)

Move or rename [Claude Code](https://claude.ai/claude-code) projects without losing session history, memory, and context.

## The Problem

When you move or rename a project directory, Claude Code loses all your session history because sessions are keyed to the absolute path of your project. You end up with orphaned data in `~/.claude/projects/` and a fresh start.

**claudepath** fixes this by updating all path references in Claude Code's data files after a move.

## Installation

```bash
# With pipx (recommended — isolated install)
pipx install claudepath

# With pip
pip install claudepath
```

### Homebrew (macOS/Linux)

```bash
brew tap Mahiler1909/tools
brew install claudepath
```

## Usage

### Move a project

Moves the directory on disk **and** updates all Claude Code references:

```bash
claudepath mv ~/old/location/my-project ~/new/location/my-project
```

### Remap after a manual move

If you already moved the directory yourself, just update Claude's references:

```bash
claudepath remap ~/old/location/my-project ~/new/location/my-project
```

### Preview changes (dry run)

See exactly what would change without modifying anything:

```bash
claudepath mv ~/old/path ~/new/path --dry-run
```

### List tracked projects

```bash
claudepath list
```

### Merge sessions when destination already has Claude data

If you opened Claude Code at the new location before running `claudepath remap`, Claude Code will have already created a new project directory there. Use `--merge` to combine the sessions from both directories:

```bash
claudepath remap ~/old/path ~/new/path --merge
```

Without `--merge`, claudepath will fail with a clear error suggesting you add the flag.

### Full help

```bash
claudepath help
claudepath mv --help
```

## What it updates

| File / Directory | What changes |
|---|---|
| `~/.claude/projects/{encoded-dir}/` | Renamed to match new path |
| `sessions-index.json` | `originalPath`, `projectPath`, `fullPath` updated (proper JSON parsing) |
| `{session}.jsonl` files | `cwd` and file path references updated (line-by-line, handles large files) |
| Subagent `.jsonl` files | Same as above, recursive |
| `~/.claude/history.jsonl` | `project` field updated for all matching entries |

> **Note:** `file-history/`, `todos/`, `tasks/`, and `shell-snapshots/` are keyed by session UUID, not by project path — they don't need updating.

## Options

| Flag | Description |
|---|---|
| `--dry-run` | Preview all changes without writing anything |
| `--no-backup` | Skip creating a backup before modifying files |
| `--yes` / `-y` | Skip the confirmation prompt |
| `--merge` | Merge sessions when destination already has Claude data |
| `--claude-dir <path>` | Override the Claude data directory (default: `~/.claude`) |

## Backup & Rollback

By default, claudepath creates a backup before making any changes:

```
~/.claude/backups/claudepath/{timestamp}/
```

The backup includes:
- The full project data directory (`~/.claude/projects/{encoded}/`)
- `~/.claude/history.jsonl`
- When using `--merge`: both the source and destination project directories

If any step fails, claudepath automatically restores from the backup. Use `--no-backup` only if you already have your own backup or want to skip the extra time.

## How Claude Code encodes paths

Claude Code stores project data in `~/.claude/projects/` using an encoded directory name: every `/` in the absolute path is replaced with `-`.

```
/Users/foo/my-project  →  -Users-foo-my-project
```

This means moving `/Users/foo/old-name` to `/Users/foo/new-name` requires:
1. Renaming `-Users-foo-old-name` to `-Users-foo-new-name`
2. Updating all path strings inside the data files

## License

MIT
