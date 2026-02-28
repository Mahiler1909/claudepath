"""
Orchestrator for mv and remap operations.
"""

import os
import shutil
import sys
from pathlib import Path
from typing import Optional, Tuple

from claudepath.backup import create_backup, get_backup_base, restore_backup
from claudepath.encoder import encode_path
from claudepath.scanner import find_claude_dir, find_project_dir
from claudepath.updaters import merge_sessions_index, update_history, update_jsonl_files, update_sessions_index


class MoveError(Exception):
    """Raised when a move/remap operation fails."""


class MoveResult:
    """Result of a move/remap operation."""

    def __init__(self):
        self.project_dir_renamed = False
        self.sessions_merged = 0
        self.sessions_index_updated = 0
        self.jsonl_files_updated = 0
        self.jsonl_lines_changed = 0
        self.history_lines_changed = 0
        self.backup_path: Optional[Path] = None
        self.dry_run = False

    def summary(self) -> str:
        prefix = "[DRY RUN] Would have: " if self.dry_run else ""
        lines = []
        if self.project_dir_renamed:
            lines.append(f"{prefix}renamed project directory in ~/.claude/projects/")
        if self.sessions_merged:
            lines.append(
                f"{prefix}merged {self.sessions_merged} session(s) from old directory into new"
            )
        if self.sessions_index_updated:
            lines.append(f"{prefix}updated sessions-index.json")
        if self.jsonl_files_updated:
            lines.append(
                f"{prefix}updated {self.jsonl_files_updated} session file(s) "
                f"({self.jsonl_lines_changed} line(s) changed)"
            )
        if self.history_lines_changed:
            lines.append(
                f"{prefix}updated {self.history_lines_changed} line(s) in history.jsonl"
            )
        if self.backup_path:
            lines.append(f"backup saved to: {self.backup_path}")
        if not lines:
            lines.append(
                "nothing to update (project may not be tracked by Claude Code)\n"
                "  Tip: run 'claudepath list' to see tracked projects."
            )
        return "\n".join(f"  - {l}" for l in lines)


def _rename_and_update(
    project_dir: Optional[Path],
    new_project_dir: Path,
    history_path: Path,
    old_path: str,
    new_path: str,
    new_encoded: str,
    dry_run: bool,
    merge: bool,
    verbose: bool,
    result: "MoveResult",
) -> None:
    """Rename (or merge) the encoded project dir and update all data files."""
    if project_dir and project_dir.exists():
        if new_project_dir.exists():
            if not merge:
                raise MoveError(
                    f"Destination Claude data directory already exists: {new_project_dir}\n"
                    "Use --merge to combine sessions from both directories."
                )
            src_index = project_dir / "sessions-index.json"
            dst_index = new_project_dir / "sessions-index.json"
            result.sessions_merged = merge_sessions_index(
                dst_index, src_index, old_path, new_path, new_encoded, dry_run=dry_run
            )
            _merge_project_dirs(project_dir, new_project_dir, dry_run)
        else:
            if not dry_run:
                os.rename(project_dir, new_project_dir)
        result.project_dir_renamed = True
        working_project_dir = new_project_dir
    else:
        working_project_dir = project_dir

    _update_data_files(
        working_project_dir,
        history_path,
        old_path,
        new_path,
        new_encoded,
        dry_run,
        result,
        verbose=verbose,
    )


def _merge_project_dirs(src: Path, dst: Path, dry_run: bool) -> int:
    """Copy all files from src into dst, skipping sessions-index.json.

    sessions-index.json is handled separately by merge_sessions_index() before
    this function is called, so we must not overwrite the merged result.

    Returns the number of .jsonl files copied from src.
    """
    src_jsonl = list(src.rglob("*.jsonl"))
    if dry_run:
        return len(src_jsonl)

    for item in src.rglob("*"):
        if item.name == "sessions-index.json":
            continue
        relative = item.relative_to(src)
        dest_item = dst / relative
        if item.is_dir():
            dest_item.mkdir(parents=True, exist_ok=True)
        else:
            dest_item.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(item), str(dest_item))

    shutil.rmtree(str(src))
    return len(src_jsonl)


def _prepare_operation(
    old_path: str,
    new_path: str,
    claude_dir: Optional[Path],
    dry_run: bool,
    no_backup: bool,
    merge: bool = False,
    verbose: bool = False,
) -> Tuple[MoveResult, Optional[Path], Path, Path, str]:
    """Resolve paths, initialize result, and create backup if needed.

    Returns (result, project_dir, new_project_dir, history_path, new_encoded).
    """
    if claude_dir is None:
        claude_dir = find_claude_dir()

    result = MoveResult()
    result.dry_run = dry_run

    project_dir = find_project_dir(claude_dir, old_path)
    new_encoded = encode_path(new_path)
    new_project_dir = claude_dir / "projects" / new_encoded
    history_path = claude_dir / "history.jsonl"

    if verbose:
        print(f"  Claude dir: {claude_dir}", file=sys.stderr)
        if project_dir:
            print(f"  Found project: {project_dir.name}", file=sys.stderr)
        else:
            print("  Project not found in Claude data", file=sys.stderr)

    if project_dir and not dry_run and not no_backup:
        backup_base = get_backup_base(claude_dir)
        extra_dir = new_project_dir if (merge and new_project_dir.exists()) else None
        result.backup_path = create_backup(project_dir, history_path, backup_base, extra_dir=extra_dir)
        if verbose:
            print(f"  Backup created: {result.backup_path}", file=sys.stderr)

    return result, project_dir, new_project_dir, history_path, new_encoded


def preview_operation(
    old_path: str,
    claude_dir: Optional[Path] = None,
) -> dict:
    """Preview what a move/remap operation would change without modifying anything.

    Returns a dict with counts for display in the confirmation prompt.
    """
    if claude_dir is None:
        claude_dir = find_claude_dir()

    project_dir = find_project_dir(claude_dir, old_path)
    history_path = claude_dir / "history.jsonl"

    info = {
        "project_found": project_dir is not None,
        "session_count": 0,
        "has_history": history_path.exists(),
    }

    if project_dir and project_dir.exists():
        info["session_count"] = len(list(project_dir.rglob("*.jsonl")))

    return info


def move_project(
    old_path: str,
    new_path: str,
    claude_dir: Optional[Path] = None,
    dry_run: bool = False,
    no_backup: bool = False,
    merge: bool = False,
    verbose: bool = False,
) -> MoveResult:
    """Move a project directory and update all Claude Code references.

    Steps:
    1. Validate paths
    2. Find encoded project dir in ~/.claude/projects/
    3. Create backup (unless --no-backup)
    4. Move the actual project directory on disk
    5. Rename (or merge) the encoded project dir
    6. Update sessions-index.json
    7. Update all .jsonl session files
    8. Update history.jsonl
    9. Return result summary

    On failure after backup, automatically restores from backup.
    """
    old_path = str(Path(old_path).resolve())
    new_path = str(Path(new_path).resolve())

    if old_path == new_path:
        raise MoveError("Source and destination are the same path.")

    old_dir = Path(old_path)
    new_dir = Path(new_path)

    if not old_dir.exists():
        raise MoveError(f"Source directory does not exist: {old_path}")
    if new_dir.exists() and any(new_dir.iterdir()):
        raise MoveError(
            f"Destination directory already exists and is not empty: {new_path}\n"
            "If you already moved the files manually, use 'claudepath remap' instead."
        )

    result, project_dir, new_project_dir, history_path, new_encoded = _prepare_operation(
        old_path, new_path, claude_dir, dry_run, no_backup, merge=merge, verbose=verbose
    )

    try:
        # Move the real project directory
        if not dry_run:
            if new_dir.exists():
                shutil.rmtree(new_dir)
            shutil.move(str(old_dir), str(new_dir))

        _rename_and_update(
            project_dir, new_project_dir, history_path,
            old_path, new_path, new_encoded,
            dry_run, merge, verbose, result,
        )

    except (OSError, MoveError) as e:
        # Rollback: restore the real directory and Claude data
        if result.backup_path and not dry_run:
            restore_backup(result.backup_path)
            # Also put the real directory back if it was moved
            if new_dir.exists() and not old_dir.exists():
                shutil.move(str(new_dir), str(old_dir))
        if isinstance(e, MoveError):
            raise
        raise MoveError(f"Move failed: {e}\nChanges have been rolled back.") from e

    return result


def remap_project(
    old_path: str,
    new_path: str,
    claude_dir: Optional[Path] = None,
    dry_run: bool = False,
    no_backup: bool = False,
    merge: bool = False,
    verbose: bool = False,
) -> MoveResult:
    """Remap Claude Code references after a project was already moved manually.

    Same as move_project but skips moving the actual directory on disk.
    Validates that new_path exists before proceeding.
    """
    old_path = str(Path(old_path).resolve())
    new_path = str(Path(new_path).resolve())

    if old_path == new_path:
        raise MoveError("Source and destination are the same path.")

    new_dir = Path(new_path)
    if not new_dir.exists():
        raise MoveError(
            f"Destination directory does not exist: {new_path}\n"
            "The directory must already exist for 'remap'. "
            "Use 'claudepath mv' if you haven't moved it yet."
        )

    result, project_dir, new_project_dir, history_path, new_encoded = _prepare_operation(
        old_path, new_path, claude_dir, dry_run, no_backup, merge=merge, verbose=verbose
    )

    try:
        _rename_and_update(
            project_dir, new_project_dir, history_path,
            old_path, new_path, new_encoded,
            dry_run, merge, verbose, result,
        )

    except (OSError, MoveError) as e:
        if result.backup_path and not dry_run:
            restore_backup(result.backup_path)
        if isinstance(e, MoveError):
            raise
        raise MoveError(f"Remap failed: {e}\nChanges have been rolled back.") from e

    return result


def _update_data_files(
    project_dir: Optional[Path],
    history_path: Path,
    old_path: str,
    new_path: str,
    new_encoded: str,
    dry_run: bool,
    result: MoveResult,
    verbose: bool = False,
) -> None:
    """Update sessions-index.json, .jsonl files, and history.jsonl."""
    if project_dir and project_dir.exists():
        index_path = project_dir / "sessions-index.json"
        result.sessions_index_updated = update_sessions_index(
            index_path, old_path, new_path, new_encoded, dry_run=dry_run, verbose=verbose
        )

        files_updated, lines_changed = update_jsonl_files(
            project_dir, old_path, new_path, dry_run=dry_run, verbose=verbose
        )
        result.jsonl_files_updated = files_updated
        result.jsonl_lines_changed = lines_changed

    result.history_lines_changed = update_history(
        history_path, old_path, new_path, dry_run=dry_run, verbose=verbose
    )
