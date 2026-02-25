"""
Scanner for Claude Code project data in ~/.claude/.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional

from claudepath.encoder import encode_path


def find_claude_dir() -> Path:
    """Return the ~/.claude directory path."""
    return Path.home() / ".claude"


def find_project_dir(claude_dir: Path, project_path: str) -> Optional[Path]:
    """Find the encoded project directory in ~/.claude/projects/ for a given absolute path.

    Tries the computed encoded name first. Falls back to scanning sessions-index.json
    files if the computed name doesn't match (handles edge cases like manually-moved
    projects where originalPath diverged from the directory name).

    Returns the Path to the project dir, or None if not found.
    """
    projects_dir = claude_dir / "projects"
    if not projects_dir.exists():
        return None

    # Primary: match by computed encoding
    encoded = encode_path(project_path)
    candidate = projects_dir / encoded
    if candidate.exists():
        return candidate

    # Fallback: scan sessions-index.json files for matching originalPath or projectPath
    normalized = str(Path(project_path).resolve())
    for entry in projects_dir.iterdir():
        if not entry.is_dir():
            continue
        index_file = entry / "sessions-index.json"
        if not index_file.exists():
            continue
        try:
            data = json.loads(index_file.read_text(encoding="utf-8"))
            original = data.get("originalPath", "")
            if str(Path(original).resolve()) == normalized:
                return entry
            # Also check first entry's projectPath
            entries = data.get("entries", [])
            if entries:
                pp = entries[0].get("projectPath", "")
                if str(Path(pp).resolve()) == normalized:
                    return entry
        except (json.JSONDecodeError, OSError):
            continue

    return None


def list_projects(claude_dir: Path) -> List[Dict]:
    """List all Claude Code projects with metadata.

    Returns a list of dicts with keys:
        - encoded_name: the directory name under ~/.claude/projects/
        - project_path: the original absolute project path (from sessions-index or best guess)
        - session_count: number of .jsonl session files
        - last_modified: ISO timestamp of most recently modified session file
    """
    projects_dir = claude_dir / "projects"
    if not projects_dir.exists():
        return []

    results = []
    for entry in sorted(projects_dir.iterdir()):
        if not entry.is_dir():
            continue

        project_path = None
        last_modified = None
        session_count = 0

        # Try to read project path from sessions-index.json
        index_file = entry / "sessions-index.json"
        if index_file.exists():
            try:
                data = json.loads(index_file.read_text(encoding="utf-8"))
                project_path = data.get("originalPath")
                entries = data.get("entries", [])
                session_count = len(entries)
                if entries:
                    last_modified = max(
                        (e.get("modified", "") for e in entries), default=None
                    )
            except (json.JSONDecodeError, OSError):
                pass

        # Count jsonl files as fallback for session count
        if session_count == 0:
            jsonl_files = list(entry.glob("*.jsonl"))
            session_count = len(jsonl_files)
            if jsonl_files and last_modified is None:
                most_recent = max(jsonl_files, key=lambda f: f.stat().st_mtime)
                import datetime
                last_modified = datetime.datetime.fromtimestamp(
                    most_recent.stat().st_mtime
                ).isoformat()

        # Derive project path from encoded name if still unknown
        if not project_path:
            # Best-effort: replace leading hyphen with / and remaining - with /
            # This is ambiguous but better than nothing for display
            project_path = entry.name.replace("-", "/", 1)

        results.append(
            {
                "encoded_name": entry.name,
                "project_path": project_path,
                "session_count": session_count,
                "last_modified": last_modified,
            }
        )

    return results
