"""
End-to-end tests for move_project and remap_project.
"""

import json
import shutil
from pathlib import Path

import pytest

from claudepath.mover import MoveError, move_project, remap_project


OLD_PATH_NAME = "old-project"
NEW_PATH_NAME = "new-project"


def make_test_env(tmp_path: Path):
    """Create a minimal test environment with a real project dir and Claude data.

    Returns (old_project, new_project_parent, claude_dir)
    """
    # Real project directories
    projects_root = tmp_path / "projects"
    old_project = projects_root / OLD_PATH_NAME
    old_project.mkdir(parents=True)
    (old_project / "main.py").write_text("print('hello')")

    # Claude data dir
    claude_dir = tmp_path / ".claude"
    old_abs = str(old_project)
    old_encoded = old_abs.replace("/", "-")

    project_data_dir = claude_dir / "projects" / old_encoded
    project_data_dir.mkdir(parents=True)

    # sessions-index.json
    index = {
        "version": 1,
        "originalPath": old_abs,
        "entries": [
            {
                "sessionId": "sess-001",
                "projectPath": old_abs,
                "fullPath": f"{claude_dir}/projects/{old_encoded}/sess-001.jsonl",
                "firstPrompt": "hello",
                "summary": "test",
                "messageCount": 2,
                "created": "2026-01-01T00:00:00.000Z",
                "modified": "2026-01-02T00:00:00.000Z",
                "gitBranch": "",
                "isSidechain": False,
            }
        ],
    }
    (project_data_dir / "sessions-index.json").write_text(json.dumps(index, indent=2))

    # Session JSONL
    session_lines = [
        json.dumps({"type": "user", "cwd": old_abs, "message": {"content": "hi"}}),
        json.dumps({"type": "assistant", "cwd": old_abs, "message": {"content": "hello"}}),
    ]
    (project_data_dir / "sess-001.jsonl").write_text("\n".join(session_lines) + "\n")

    # Subagent JSONL
    subagents_dir = project_data_dir / "sess-001" / "subagents"
    subagents_dir.mkdir(parents=True)
    (subagents_dir / "agent-abc.jsonl").write_text(
        json.dumps({"type": "user", "cwd": old_abs}) + "\n"
    )

    # history.jsonl
    history = claude_dir / "history.jsonl"
    history.write_text(
        json.dumps({"display": "cmd", "project": old_abs, "timestamp": 1000}) + "\n"
        + json.dumps({"display": "other", "project": "/other/path", "timestamp": 1001}) + "\n"
    )

    return old_project, projects_root, claude_dir


# ─── move_project ──────────────────────────────────────────────────────────

def test_move_project_moves_directory(tmp_path):
    old_project, projects_root, claude_dir = make_test_env(tmp_path)
    new_project = projects_root / NEW_PATH_NAME

    move_project(str(old_project), str(new_project), claude_dir=claude_dir, no_backup=True)

    assert not old_project.exists()
    assert new_project.exists()
    assert (new_project / "main.py").exists()


def test_move_project_renames_claude_project_dir(tmp_path):
    old_project, projects_root, claude_dir = make_test_env(tmp_path)
    new_project = projects_root / NEW_PATH_NAME
    new_encoded = str(new_project).replace("/", "-")

    move_project(str(old_project), str(new_project), claude_dir=claude_dir, no_backup=True)

    assert (claude_dir / "projects" / new_encoded).exists()
    old_encoded = str(old_project).replace("/", "-")
    assert not (claude_dir / "projects" / old_encoded).exists()


def test_move_project_updates_sessions_index(tmp_path):
    old_project, projects_root, claude_dir = make_test_env(tmp_path)
    new_project = projects_root / NEW_PATH_NAME
    new_encoded = str(new_project).replace("/", "-")

    move_project(str(old_project), str(new_project), claude_dir=claude_dir, no_backup=True)

    index_path = claude_dir / "projects" / new_encoded / "sessions-index.json"
    data = json.loads(index_path.read_text())
    assert data["originalPath"] == str(new_project)
    assert data["entries"][0]["projectPath"] == str(new_project)
    assert new_encoded in data["entries"][0]["fullPath"]


def test_move_project_updates_jsonl_cwd(tmp_path):
    old_project, projects_root, claude_dir = make_test_env(tmp_path)
    new_project = projects_root / NEW_PATH_NAME
    new_encoded = str(new_project).replace("/", "-")
    new_abs = str(new_project)

    move_project(str(old_project), str(new_project), claude_dir=claude_dir, no_backup=True)

    session_file = claude_dir / "projects" / new_encoded / "sess-001.jsonl"
    content = session_file.read_text()
    assert str(old_project) not in content
    assert new_abs in content


def test_move_project_updates_subagent_jsonl(tmp_path):
    old_project, projects_root, claude_dir = make_test_env(tmp_path)
    new_project = projects_root / NEW_PATH_NAME
    new_encoded = str(new_project).replace("/", "-")

    move_project(str(old_project), str(new_project), claude_dir=claude_dir, no_backup=True)

    agent_file = claude_dir / "projects" / new_encoded / "sess-001" / "subagents" / "agent-abc.jsonl"
    content = agent_file.read_text()
    assert str(old_project) not in content
    assert str(new_project) in content


def test_move_project_updates_history(tmp_path):
    old_project, projects_root, claude_dir = make_test_env(tmp_path)
    new_project = projects_root / NEW_PATH_NAME

    move_project(str(old_project), str(new_project), claude_dir=claude_dir, no_backup=True)

    history_lines = [
        json.loads(l) for l in (claude_dir / "history.jsonl").read_text().splitlines() if l.strip()
    ]
    assert history_lines[0]["project"] == str(new_project)
    assert history_lines[1]["project"] == "/other/path"  # untouched


def test_move_project_dry_run_no_changes(tmp_path):
    old_project, projects_root, claude_dir = make_test_env(tmp_path)
    new_project = projects_root / NEW_PATH_NAME

    # Capture original state
    old_encoded = str(old_project).replace("/", "-")
    original_index = (claude_dir / "projects" / old_encoded / "sessions-index.json").read_text()
    original_session = (claude_dir / "projects" / old_encoded / "sess-001.jsonl").read_text()
    original_history = (claude_dir / "history.jsonl").read_text()

    move_project(
        str(old_project), str(new_project), claude_dir=claude_dir, dry_run=True, no_backup=True
    )

    # Nothing should have changed
    assert old_project.exists()
    assert not new_project.exists()
    assert (claude_dir / "projects" / old_encoded).exists()
    assert (claude_dir / "projects" / old_encoded / "sessions-index.json").read_text() == original_index
    assert (claude_dir / "projects" / old_encoded / "sess-001.jsonl").read_text() == original_session
    assert (claude_dir / "history.jsonl").read_text() == original_history


def test_move_project_fails_if_source_missing(tmp_path):
    _, projects_root, claude_dir = make_test_env(tmp_path)
    with pytest.raises(MoveError, match="does not exist"):
        move_project("/nonexistent/path", str(projects_root / "new"), claude_dir=claude_dir)


def test_move_project_fails_if_dest_nonempty(tmp_path):
    old_project, projects_root, claude_dir = make_test_env(tmp_path)
    new_project = projects_root / NEW_PATH_NAME
    new_project.mkdir()
    (new_project / "existing.txt").write_text("existing")

    with pytest.raises(MoveError, match="not empty"):
        move_project(str(old_project), str(new_project), claude_dir=claude_dir)


# ─── remap_project ─────────────────────────────────────────────────────────

def test_remap_project_updates_references_without_moving(tmp_path):
    old_project, projects_root, claude_dir = make_test_env(tmp_path)
    new_project = projects_root / NEW_PATH_NAME

    # Move directory manually first
    shutil.move(str(old_project), str(new_project))

    remap_project(str(old_project), str(new_project), claude_dir=claude_dir, no_backup=True)

    # Old project dir on disk should not be restored
    assert not old_project.exists()
    assert new_project.exists()

    # Claude data should be updated
    new_encoded = str(new_project).replace("/", "-")
    assert (claude_dir / "projects" / new_encoded).exists()
    data = json.loads((claude_dir / "projects" / new_encoded / "sessions-index.json").read_text())
    assert data["originalPath"] == str(new_project)


def test_remap_project_fails_if_new_path_missing(tmp_path):
    old_project, projects_root, claude_dir = make_test_env(tmp_path)
    with pytest.raises(MoveError, match="does not exist"):
        remap_project(str(old_project), "/nonexistent/new/path", claude_dir=claude_dir)


# ─── backup ────────────────────────────────────────────────────────────────

def test_move_project_creates_backup(tmp_path):
    old_project, projects_root, claude_dir = make_test_env(tmp_path)
    new_project = projects_root / NEW_PATH_NAME

    result = move_project(str(old_project), str(new_project), claude_dir=claude_dir)

    assert result.backup_path is not None
    assert result.backup_path.exists()
    assert (result.backup_path / "history.jsonl").exists()
    assert (result.backup_path / "project_dir").exists()
