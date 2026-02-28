"""
Updaters for Claude Code data files after a project move/remap.

All updaters support dry_run mode: they compute what would change but do not
write anything. They return a count of files/lines modified.
"""

import json
import os
import sys
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
    verbose: bool = False,
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

    if verbose and changed:
        fields = []
        if data.get("originalPath") == new_path:
            fields.append("originalPath")
        fields.append("projectPath")
        fields.append("fullPath")
        print(f"    {index_path.name}: updated {', '.join(fields)}", file=sys.stderr)

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
    verbose: bool = False,
) -> Tuple[int, int]:
    """Replace all occurrences of old_path with new_path in every .jsonl file
    inside project_dir (recursively, including subagent dirs).

    Processes files line-by-line to handle large sessions (>9MB).

    Returns (files_updated, total_lines_changed).
    """
    files_updated = 0
    total_lines_changed = 0

    for jsonl_file in project_dir.rglob("*.jsonl"):
        lines_changed = replace_in_file(jsonl_file, old_path, new_path, dry_run)
        if lines_changed > 0:
            files_updated += 1
            total_lines_changed += lines_changed
            if verbose:
                rel = jsonl_file.relative_to(project_dir)
                print(f"    {rel}: {lines_changed} line(s) changed", file=sys.stderr)

    return files_updated, total_lines_changed


def update_history(
    history_path: Path,
    old_path: str,
    new_path: str,
    dry_run: bool = False,
    verbose: bool = False,
) -> int:
    """Replace old_path with new_path in ~/.claude/history.jsonl.

    The history file has lines like:
        {"display":"...","project":"/old/path","timestamp":...}

    Returns the number of lines changed.
    """
    if not history_path.exists():
        return 0
    count = replace_in_file(history_path, old_path, new_path, dry_run)
    if verbose and count:
        print(f"    history.jsonl: {count} line(s) changed", file=sys.stderr)
    return count


def merge_sessions_index(
    dst_index: Path,
    src_index: Path,
    old_path: str,
    new_path: str,
    new_encoded: str,
    dry_run: bool = False,
) -> int:
    """Merge entries from src sessions-index.json into dst sessions-index.json.

    Entries from src are updated (old_path → new_path) before being appended.
    Entries that already exist in dst (by sessionId) are skipped.

    Returns the number of entries merged from src into dst.
    """
    if not dst_index.exists() or not src_index.exists():
        return 0

    try:
        dst_data = json.loads(dst_index.read_text(encoding="utf-8"))
        src_data = json.loads(src_index.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return 0

    old_encoded = encode_path(old_path)
    existing_ids = {e.get("sessionId") for e in dst_data.get("entries", [])}

    merged = 0
    for entry in src_data.get("entries", []):
        if entry.get("sessionId") in existing_ids:
            print(
                f"  Warning: skipping duplicate session '{entry.get('sessionId')}'",
                file=sys.stderr,
            )
            continue
        # Update paths in the entry
        if entry.get("projectPath") == old_path:
            entry["projectPath"] = new_path
        full_path = entry.get("fullPath", "")
        if old_encoded in full_path:
            entry["fullPath"] = full_path.replace(old_encoded, new_encoded, 1)
        dst_data.setdefault("entries", []).append(entry)
        merged += 1

    # Ensure originalPath is updated
    if dst_data.get("originalPath") == old_path:
        dst_data["originalPath"] = new_path

    if merged > 0 and not dry_run:
        dst_index.write_text(
            json.dumps(dst_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    return merged


def replace_path_values(obj, old: str, new: str) -> bool:
    """Recursively replace path values in a parsed JSON object.

    Only replaces string values that are exactly `old` or start with `old/`.
    Returns True if any replacement was made.
    """
    changed = False
    if isinstance(obj, dict):
        items = obj.keys()
    elif isinstance(obj, list):
        items = range(len(obj))
    else:
        return False
    for key in items:
        val = obj[key]
        if isinstance(val, str):
            if val == old or val.startswith(old + "/"):
                obj[key] = new + val[len(old):]
                changed = True
        elif isinstance(val, (dict, list)):
            if replace_path_values(val, old, new):
                changed = True
    return changed


def replace_in_file(file_path: Path, old: str, new: str, dry_run: bool) -> int:
    """Replace path references of `old` with `new` in a JSONL file, line by line.

    Each line is parsed as JSON for safe, targeted replacement of path values.
    Only string values that are exactly `old` or start with `old/` are replaced,
    preventing substring corruption (e.g., /Users/foo won't match /Users/foobar).

    Falls back to string replacement for lines that aren't valid JSON.

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
        if old not in line:
            new_lines.append(line)
            continue

        stripped = line.rstrip("\n\r")
        try:
            obj = json.loads(stripped)
            if replace_path_values(obj, old, new):
                new_lines.append(json.dumps(obj, ensure_ascii=False) + "\n")
                lines_changed += 1
            else:
                new_lines.append(line)
        except (json.JSONDecodeError, ValueError):
            # Fallback for non-JSON lines: use exact-or-prefix string replacement
            new_lines.append(line.replace(old, new))
            lines_changed += 1

    if lines_changed > 0 and not dry_run:
        # Write atomically: write to temp file in same dir, then rename
        dir_path = file_path.parent
        fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
            os.replace(tmp_path, file_path)
        except OSError:
            os.unlink(tmp_path)
            raise

    return lines_changed
