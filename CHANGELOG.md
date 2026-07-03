# Changelog

## [1.1.2] - 2026-07-03

### Fixed
- **Path encoding now matches Claude Code's actual algorithm** ([#2](https://github.com/Mahiler1909/claudepath/issues/2), [#4](https://github.com/Mahiler1909/claudepath/pull/4) by @gmasse): every non-ASCII-alphanumeric character (`.`, `_`, `~`, spaces, non-ASCII, …) is replaced with `-`, not just `/`. Encoded names longer than 200 chars are truncated and suffixed with a base-36 hash. Previously, paths containing these characters were silently missed by `mv` and `remap`
- `find_project_dir` now falls back to reading the `cwd` field from `.jsonl` files when `sessions-index.json` is missing or corrupted ([#4](https://github.com/Mahiler1909/claudepath/pull/4))
- File mtimes are preserved when rewriting session and history files ([#3](https://github.com/Mahiler1909/claudepath/pull/3) by @johnowennixon) — Claude Code's project list sorts by session mtime, so rewrites no longer reorder every touched session to the top

## [1.1.1] - 2026-03-05

### Improved
- `claudepath list` now shows a summary line with project count at the end (e.g., "13 projects (12 on disk, 1 orphaned)")
- `claudepath help` now lists `usage-data/session-meta/*.json` in the "WHAT IT UPDATES" section

## [1.1.0] - 2026-03-05

### Added
- `usage-data/session-meta/*.json` files are now updated during `mv` and `remap` — fixes stale `project_path` in token usage and analytics data
- Usage-data files are included in automatic backups and restored on rollback
- Backup is now created even when the encoded project directory is not found (e.g., usage-data-only remaps)

## [1.0.0] - 2026-02-27

### Added
- `claudepath restore` command: list and restore from automatic backups (`--list`, `<timestamp>`)
- `claudepath update` command: self-update with auto-detection of install method (Homebrew, pipx, or pip)
- `--verbose` / `-v` flag for `mv` and `remap`: show detailed file-by-file processing output
- Per-command `--help` support (e.g., `claudepath mv --help`)
- "Did you mean?" suggestions for mistyped commands (e.g., `mov` → `mv`)
- `NO_COLOR` and `FORCE_COLOR` environment variable support (standard convention)
- `list` command now shows project existence status on disk (✓ on disk / ✗ orphaned)
- Better confirmation prompts showing preview of what will change (file counts, backup info)
- Improved error messages with usage hints and suggestions
- Warning when Claude Code may be actively using the project

### Fixed
- **Critical:** JSONL path replacement is now JSON-aware — prevents substring corruption (e.g., `/Users/foo` no longer incorrectly modifies `/Users/foobar`)
- **Critical:** Atomic file writes now properly propagate exceptions instead of silently returning success
- **Critical:** Backup restore uses atomic rename-aside strategy — if copy fails, original directory is preserved
- Merge now warns when duplicate session IDs are skipped instead of silently discarding them
- "Nothing to update" message now suggests `claudepath list` to help users find tracked projects

## [0.4.0] - 2026-02-27

### Added
- `--merge` flag for `mv` and `remap`: when the destination Claude data directory already exists (because Claude Code was opened at the new location before running claudepath), `--merge` combines sessions from both directories instead of failing with "Directory not empty"
- Backup now includes both source and destination directories when `--merge` is used, enabling full rollback

### Fixed
- `remap` and `mv` now raise a clear error with a `--merge` hint when the destination Claude data directory already exists, instead of crashing with an opaque `Errno 66` message

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
