# Changelog

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
