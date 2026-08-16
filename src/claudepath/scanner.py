"""
Scanner for Claude Code project data in ~/.claude/.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from claudepath.encoder import encode_path


def find_claude_dir() -> Path:
    """Return the ~/.claude directory path."""
    return Path.home() / ".claude"


def find_config_file(claude_dir: Path) -> Path:
    """Return the .claude.json config file sitting alongside `claude_dir`.

    Claude Code stores per-project config in ~/.claude.json — a sibling of the
    ~/.claude data directory, not a file inside it.
    """
    return claude_dir.parent / ".claude.json"


def find_project_dir(claude_dir: Path, project_path: str) -> Optional[Path]:
    """Find the encoded project directory in ~/.claude/projects/ for a given absolute path.

    Tries the computed encoded name first. Falls back to scanning sessions-index.json
    files, then to reading the cwd field from .jsonl files (handles cases where
    sessions-index.json is missing or corrupted).

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

    # Fallback: scan each project dir for any signal pointing at project_path.
    # First try sessions-index.json; if that's missing/invalid, probe a .jsonl cwd field.
    normalized = str(Path(project_path).resolve())
    for entry in projects_dir.iterdir():
        if not entry.is_dir():
            continue

        matched_via_index = False
        index_file = entry / "sessions-index.json"
        if index_file.exists():
            try:
                data = json.loads(index_file.read_text(encoding="utf-8"))
                matched_via_index = True
                original = data.get("originalPath", "")
                if original and str(Path(original).resolve()) == normalized:
                    return entry
                entries = data.get("entries", [])
                if entries:
                    pp = entries[0].get("projectPath", "")
                    if pp and str(Path(pp).resolve()) == normalized:
                        return entry
            except (json.JSONDecodeError, OSError):
                matched_via_index = False

        # If the index didn't resolve the path (missing, invalid, or null fields),
        # peek at any .jsonl file's cwd — it always carries the real project path.
        if not matched_via_index or _index_lacks_path(index_file):
            cwd = _read_first_cwd_in_dir(entry)
            if cwd and str(Path(cwd).resolve()) == normalized:
                return entry

    return None


def _index_lacks_path(index_file: Path) -> bool:
    """Return True if sessions-index.json has no usable originalPath/projectPath."""
    if not index_file.exists():
        return True
    try:
        data = json.loads(index_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return True
    if data.get("originalPath"):
        return False
    entries = data.get("entries", [])
    return not (entries and entries[0].get("projectPath"))


def _read_first_cwd_in_dir(project_dir: Path) -> Optional[str]:
    """Return the cwd from the first .jsonl that has one, or None."""
    for jsonl_file in project_dir.glob("*.jsonl"):
        cwd = _read_cwd_from_jsonl(jsonl_file)
        if cwd:
            return cwd
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


def collect_project_state(claude_dir: Path, project_path: str) -> Dict:
    """Gather every piece of Claude Code state attached to `project_path`.

    Reports what a move would carry across, without modifying anything.

    Returns a dict with keys:
        - project_path: the resolved absolute path that was queried
        - exists_on_disk: whether the directory is still present
        - project_dir: the ~/.claude/projects/{encoded}/ Path, or None
        - session_count: number of .jsonl transcripts, subagents included
        - last_active: ISO timestamp of the newest transcript, or None
        - config_entries: number of .claude.json projects[] entries, nested included
        - history_prompts: number of history.jsonl prompts typed here
        - usage_data_files: number of usage-data/session-meta files
        - found: True if any state at all is attached to the path
    """
    resolved = str(Path(project_path).expanduser().resolve())
    project_dir = find_project_dir(claude_dir, resolved)

    session_count, last_active = _summarize_sessions(project_dir)
    state = {
        "project_path": resolved,
        "exists_on_disk": Path(resolved).is_dir(),
        "project_dir": project_dir,
        "session_count": session_count,
        "last_active": last_active,
        "config_entries": _count_config_entries(find_config_file(claude_dir), resolved),
        "history_prompts": _count_history_prompts(claude_dir / "history.jsonl", resolved),
        "usage_data_files": _count_usage_data_files(claude_dir, resolved),
    }
    state["found"] = bool(
        project_dir
        or state["config_entries"]
        or state["history_prompts"]
        or state["usage_data_files"]
    )
    return state


def _summarize_sessions(project_dir: Optional[Path]) -> Tuple[int, Optional[str]]:
    """Return (transcript count, ISO timestamp of the newest one)."""
    if not project_dir or not project_dir.exists():
        return 0, None

    transcripts = list(project_dir.rglob("*.jsonl"))
    if not transcripts:
        return 0, None

    newest = max(transcripts, key=lambda f: f.stat().st_mtime)
    return len(transcripts), datetime.fromtimestamp(newest.stat().st_mtime).isoformat()


def _count_config_entries(config_path: Path, project_path: str) -> int:
    """Count .claude.json projects[] entries for `project_path` and anything under it."""
    if not config_path.exists():
        return 0
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return 0

    projects = data.get("projects")
    if not isinstance(projects, dict):
        return 0
    return sum(
        1 for key in projects
        if key == project_path or key.startswith(project_path + "/")
    )


def _count_history_prompts(history_path: Path, project_path: str) -> int:
    """Count history.jsonl entries whose project field matches `project_path`."""
    if not history_path.exists():
        return 0

    count = 0
    try:
        with open(history_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if project_path not in line:
                    continue
                try:
                    if json.loads(line).get("project") == project_path:
                        count += 1
                except json.JSONDecodeError:
                    continue
    except OSError:
        return 0
    return count


def _count_usage_data_files(claude_dir: Path, project_path: str) -> int:
    """Count usage-data/session-meta files recording work in `project_path`."""
    meta_dir = claude_dir / "usage-data" / "session-meta"
    if not meta_dir.exists():
        return 0

    count = 0
    for json_file in meta_dir.glob("*.json"):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        recorded = data.get("project_path", "")
        if recorded == project_path or recorded.startswith(project_path + "/"):
            count += 1
    return count


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
