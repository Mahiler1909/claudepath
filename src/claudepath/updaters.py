"""
Updaters for Claude Code data files after a project move/remap.

All updaters support dry_run mode: they compute what would change but do not
write anything. They return a count of files/lines modified.
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Tuple

from claudepath.encoder import encode_path


def update_sessions_index(
    index_path: Path,
    old_path: str,
    new_path: str,
    new_encoded_dir: str,
    dry_run: bool = False,
) -> int:
    """Update sessions-index.json with the new project path.

    Updates three types of references:
    - "originalPath": the root-level original project path
    - entries[*]["projectPath"]: project path in each session entry
    - entries[*]["fullPath"]: absolute path to the .jsonl file (contains encoded dir name)

    Returns 1 if the file was updated, 0 if it did not need updating.
    """
    if not index_path.exists():
        return 0

    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return 0

    changed = False

    if data.get("originalPath") == old_path:
        data["originalPath"] = new_path
        changed = True

    old_encoded = encode_path(old_path)
    for entry in data.get("entries", []):
        if entry.get("projectPath") == old_path:
            entry["projectPath"] = new_path
            changed = True
        # fullPath looks like: /Users/foo/.claude/projects/{encoded}/{sessionId}.jsonl
        full_path = entry.get("fullPath", "")
        if old_encoded in full_path:
            entry["fullPath"] = full_path.replace(old_encoded, new_encoded_dir, 1)
            changed = True

    if changed and not dry_run:
        index_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    return 1 if changed else 0


def update_jsonl_files(
    project_dir: Path,
    old_path: str,
    new_path: str,
    dry_run: bool = False,
) -> Tuple[int, int]:
    """Replace all occurrences of old_path with new_path in every .jsonl file
    inside project_dir (recursively, including subagent dirs).

    Processes files line-by-line to handle large sessions (>9MB).

    Returns (files_updated, total_lines_changed).
    """
    files_updated = 0
    total_lines_changed = 0

    for jsonl_file in project_dir.rglob("*.jsonl"):
        lines_changed = _replace_in_file(jsonl_file, old_path, new_path, dry_run)
        if lines_changed > 0:
            files_updated += 1
            total_lines_changed += lines_changed

    return files_updated, total_lines_changed


def update_history(
    history_path: Path,
    old_path: str,
    new_path: str,
    dry_run: bool = False,
) -> int:
    """Replace old_path with new_path in ~/.claude/history.jsonl.

    The history file has lines like:
        {"display":"...","project":"/old/path","timestamp":...}

    Returns the number of lines changed.
    """
    if not history_path.exists():
        return 0
    return _replace_in_file(history_path, old_path, new_path, dry_run)


def _replace_in_file(file_path: Path, old: str, new: str, dry_run: bool) -> int:
    """Replace all occurrences of `old` with `new` in a file, line by line.

    Writes atomically via a temp file to avoid partial writes on error.
    Returns the number of lines that contained at least one replacement.
    """
    lines_changed = 0
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        return 0

    new_lines = []
    for line in lines:
        if old in line:
            new_lines.append(line.replace(old, new))
            lines_changed += 1
        else:
            new_lines.append(line)

    if lines_changed > 0 and not dry_run:
        # Write atomically: write to temp file in same dir, then rename
        dir_path = file_path.parent
        try:
            fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)
                os.replace(tmp_path, file_path)
            except Exception:
                os.unlink(tmp_path)
                raise
        except OSError:
            return 0

    return lines_changed
