import json
from pathlib import Path

from claudepath.scanner import find_project_dir, list_projects


OLD_PATH = "/Users/foo/my-project"
ENCODED = "-Users-foo-my-project"


def make_claude_dir(tmp_path: Path, project_path: str = OLD_PATH) -> tuple:
    """Create a minimal ~/.claude directory structure for testing."""
    claude_dir = tmp_path / ".claude"
    projects_dir = claude_dir / "projects"
    encoded = project_path.replace("/", "-")
    project_dir = projects_dir / encoded
    project_dir.mkdir(parents=True)

    # Create a sessions-index.json
    index = {
        "version": 1,
        "originalPath": project_path,
        "entries": [
            {
                "sessionId": "sess-001",
                "projectPath": project_path,
                "fullPath": str(project_dir / "sess-001.jsonl"),
                "firstPrompt": "hello",
                "summary": "test",
                "messageCount": 3,
                "created": "2026-01-01T00:00:00.000Z",
                "modified": "2026-01-02T00:00:00.000Z",
                "gitBranch": "",
                "isSidechain": False,
            }
        ],
    }
    (project_dir / "sessions-index.json").write_text(json.dumps(index, indent=2))
    (project_dir / "sess-001.jsonl").write_text('{"type":"user","cwd":"/old"}\n')

    return claude_dir, project_dir


def test_find_project_dir_by_encoded_name(tmp_path):
    claude_dir, project_dir = make_claude_dir(tmp_path)
    found = find_project_dir(claude_dir, OLD_PATH)
    assert found == project_dir


def test_find_project_dir_fallback_sessions_index(tmp_path):
    """If encoded name doesn't match but sessions-index has the path, still find it."""
    claude_dir = tmp_path / ".claude"
    projects_dir = claude_dir / "projects"
    # Use a wrong encoded name (simulating a manually moved project)
    wrong_encoded = "-wrong-encoded-name"
    project_dir = projects_dir / wrong_encoded
    project_dir.mkdir(parents=True)
    index = {
        "version": 1,
        "originalPath": OLD_PATH,
        "entries": [],
    }
    (project_dir / "sessions-index.json").write_text(json.dumps(index))

    found = find_project_dir(claude_dir, OLD_PATH)
    assert found == project_dir


def test_find_project_dir_not_found(tmp_path):
    claude_dir = tmp_path / ".claude"
    (claude_dir / "projects").mkdir(parents=True)
    found = find_project_dir(claude_dir, "/nonexistent/path")
    assert found is None


def test_find_project_dir_no_projects_dir(tmp_path):
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    found = find_project_dir(claude_dir, OLD_PATH)
    assert found is None


def test_list_projects_returns_metadata(tmp_path):
    claude_dir, _ = make_claude_dir(tmp_path)
    projects = list_projects(claude_dir)
    assert len(projects) == 1
    p = projects[0]
    assert p["project_path"] == OLD_PATH
    assert p["session_count"] == 1
    assert p["last_modified"] is not None


def test_list_projects_empty(tmp_path):
    claude_dir = tmp_path / ".claude"
    (claude_dir / "projects").mkdir(parents=True)
    projects = list_projects(claude_dir)
    assert projects == []


def test_list_projects_no_sessions_index(tmp_path):
    """Projects without sessions-index.json should still appear."""
    claude_dir = tmp_path / ".claude"
    project_dir = claude_dir / "projects" / "-Users-foo-bar"
    project_dir.mkdir(parents=True)
    (project_dir / "sess-001.jsonl").write_text('{"type":"user"}\n')

    projects = list_projects(claude_dir)
    assert len(projects) == 1
    assert projects[0]["session_count"] == 1
