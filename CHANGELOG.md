# Changelog

## [0.3.0] - 2026-02-26

### Added
- Update check on every command: fetches latest version from PyPI in a background thread and prints a notice if a newer version is available, showing both `pipx` and `brew` upgrade commands

## [0.2.0] - 2026-02-26

### Fixed
- `list` command now resolves real paths for all projects, including those without `sessions-index.json` or `cwd` fields in their session files
- Three-tier fallback strategy for path resolution:
  1. `originalPath` / `entries[].projectPath` from `sessions-index.json` (handles `null` originalPath bug in Claude Code)
  2. `cwd` field from `.jsonl` session files
  3. Filesystem DFS: probes the filesystem to disambiguate `-` as path separator vs hyphen in directory names

## [0.1.0] - 2026-02-25

### Added
- `claudepath mv` — move a project directory and update all Claude Code references
- `claudepath remap` — update references only (directory already moved manually)
- `claudepath list` — list all projects tracked by Claude Code
- `claudepath help` — show usage and examples
- `--dry-run` flag to preview changes without modifying files
- `--no-backup` flag to skip automatic backup
- `--yes` flag to skip confirmation prompt
- `--claude-dir` flag to override the Claude data directory
- Automatic backup to `~/.claude/backups/claudepath/{timestamp}/` before any changes
- Automatic rollback on failure
- Proper JSON parsing for `sessions-index.json` (fixes gap in existing community tools)
- Recursive update of subagent `.jsonl` files
- Line-by-line processing for large session files (>9MB)
