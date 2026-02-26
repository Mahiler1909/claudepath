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


def _decode_encoded_name(encoded_name: str) -> Optional[str]:
    """Try to recover the real absolute path from an encoded directory name
    by checking which path components actually exist on disk.

    Uses DFS with backtracking: each '-' in the name could be either a path
    separator (originally '/') or a hyphen in a directory name. We probe the
    filesystem to disambiguate.

    Returns the real path string if found, None if the project no longer exists.
    """
    # Strip leading '-' (encodes the leading '/')
    parts = encoded_name.lstrip("-").split("-")

    def dfs(current: Path, remaining: List[str]) -> Optional[Path]:
        if not remaining:
            return current
        for i in range(1, len(remaining) + 1):
            candidate = current / "-".join(remaining[:i])
            if candidate.is_dir():
                result = dfs(candidate, remaining[i:])
                if result is not None:
                    return result
        return None

    found = dfs(Path("/"), parts)
    return str(found) if found else None


def _read_cwd_from_jsonl(jsonl_file: Path) -> Optional[str]:
    """Read the cwd field from the first user/assistant message in a .jsonl file."""
    try:
        with open(jsonl_file, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    cwd = obj.get("cwd")
                    if cwd:
                        return cwd
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
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
                project_path = data.get("originalPath") or None
                entries = data.get("entries", [])
                # Fallback: use projectPath from first entry if originalPath is null
                if not project_path and entries:
                    project_path = entries[0].get("projectPath") or None
                session_count = len(entries)
                if entries:
                    last_modified = max(
                        (e.get("modified", "") for e in entries), default=None
                    )
            except (json.JSONDecodeError, OSError):
                pass

        # Count jsonl files as fallback for session count
        jsonl_files = list(entry.glob("*.jsonl"))
        if session_count == 0:
            session_count = len(jsonl_files)
            if jsonl_files and last_modified is None:
                import datetime
                most_recent = max(jsonl_files, key=lambda f: f.stat().st_mtime)
                last_modified = datetime.datetime.fromtimestamp(
                    most_recent.stat().st_mtime
                ).isoformat()

        # Fallback: read cwd from the first line of any .jsonl — always has the real path
        if not project_path and jsonl_files:
            project_path = _read_cwd_from_jsonl(jsonl_files[0])

        # Fallback: probe the filesystem to decode the encoded directory name
        if not project_path:
            project_path = _decode_encoded_name(entry.name)

        # Last resort: encoded name with leading - replaced by /
        if not project_path:
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
