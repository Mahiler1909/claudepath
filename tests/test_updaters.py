import json
from pathlib import Path

from claudepath.updaters import update_history, update_jsonl_files, update_sessions_index


OLD_PATH = "/Users/foo/old-project"
NEW_PATH = "/Users/foo/new-project"
OLD_ENCODED = "-Users-foo-old-project"
NEW_ENCODED = "-Users-foo-new-project"
CLAUDE_DIR = "/Users/foo/.claude"


# ─── sessions-index.json ───────────────────────────────────────────────────

def make_sessions_index(project_dir: Path) -> Path:
    data = {
        "version": 1,
        "originalPath": OLD_PATH,
        "entries": [
            {
                "sessionId": "abc-123",
                "projectPath": OLD_PATH,
                "fullPath": f"{CLAUDE_DIR}/projects/{OLD_ENCODED}/abc-123.jsonl",
                "firstPrompt": "hello",
                "summary": "test session",
                "messageCount": 5,
                "created": "2026-01-01T00:00:00.000Z",
                "modified": "2026-01-02T00:00:00.000Z",
                "gitBranch": "",
                "isSidechain": False,
            }
        ],
    }
    index_path = project_dir / "sessions-index.json"
    index_path.write_text(json.dumps(data, indent=2))
    return index_path


def test_update_sessions_index_updates_all_fields(tmp_path):
    index_path = make_sessions_index(tmp_path)
    count = update_sessions_index(index_path, OLD_PATH, NEW_PATH, NEW_ENCODED)
    assert count == 1

    data = json.loads(index_path.read_text())
    assert data["originalPath"] == NEW_PATH
    assert data["entries"][0]["projectPath"] == NEW_PATH
    assert OLD_ENCODED not in data["entries"][0]["fullPath"]
    assert NEW_ENCODED in data["entries"][0]["fullPath"]


def test_update_sessions_index_dry_run_does_not_write(tmp_path):
    index_path = make_sessions_index(tmp_path)
    original = index_path.read_text()
    update_sessions_index(index_path, OLD_PATH, NEW_PATH, NEW_ENCODED, dry_run=True)
    assert index_path.read_text() == original


def test_update_sessions_index_returns_zero_if_no_match(tmp_path):
    index_path = make_sessions_index(tmp_path)
    count = update_sessions_index(index_path, "/some/other/path", NEW_PATH, NEW_ENCODED)
    assert count == 0


def test_update_sessions_index_missing_file(tmp_path):
    count = update_sessions_index(
        tmp_path / "nonexistent.json", OLD_PATH, NEW_PATH, NEW_ENCODED
    )
    assert count == 0


# ─── JSONL files ───────────────────────────────────────────────────────────

def make_session_jsonl(project_dir: Path, filename: str = "abc-123.jsonl") -> Path:
    lines = [
        json.dumps({"type": "user", "cwd": OLD_PATH, "message": {"content": "hi"}}),
        json.dumps({"type": "assistant", "cwd": OLD_PATH, "message": {"content": "hello"}}),
        json.dumps({"type": "tool_result", "path": f"{OLD_PATH}/src/main.py"}),
    ]
    f = project_dir / filename
    f.write_text("\n".join(lines) + "\n")
    return f


def test_update_jsonl_files_replaces_cwd(tmp_path):
    make_session_jsonl(tmp_path)
    files_updated, lines_changed = update_jsonl_files(tmp_path, OLD_PATH, NEW_PATH)
    assert files_updated == 1
    assert lines_changed == 3  # all 3 lines contain OLD_PATH

    content = (tmp_path / "abc-123.jsonl").read_text()
    assert OLD_PATH not in content
    assert NEW_PATH in content


def test_update_jsonl_files_recursive_subagents(tmp_path):
    subagents_dir = tmp_path / "subagents"
    subagents_dir.mkdir()
    make_session_jsonl(subagents_dir, "agent-xyz.jsonl")
    make_session_jsonl(tmp_path)

    files_updated, lines_changed = update_jsonl_files(tmp_path, OLD_PATH, NEW_PATH)
    assert files_updated == 2
    assert lines_changed == 6


def test_update_jsonl_files_dry_run(tmp_path):
    f = make_session_jsonl(tmp_path)
    original = f.read_text()
    files_updated, lines_changed = update_jsonl_files(tmp_path, OLD_PATH, NEW_PATH, dry_run=True)
    assert files_updated == 1
    assert lines_changed == 3
    assert f.read_text() == original  # unchanged


def test_update_jsonl_files_no_match(tmp_path):
    make_session_jsonl(tmp_path)
    files_updated, lines_changed = update_jsonl_files(tmp_path, "/no/match", NEW_PATH)
    assert files_updated == 0
    assert lines_changed == 0


# ─── history.jsonl ─────────────────────────────────────────────────────────

def make_history(tmp_path: Path) -> Path:
    lines = [
        json.dumps({"display": "cmd1", "project": OLD_PATH, "timestamp": 1000}),
        json.dumps({"display": "cmd2", "project": "/other/project", "timestamp": 1001}),
        json.dumps({"display": "cmd3", "project": OLD_PATH, "timestamp": 1002}),
    ]
    history = tmp_path / "history.jsonl"
    history.write_text("\n".join(lines) + "\n")
    return history


def test_update_history_replaces_matching_lines(tmp_path):
    history = make_history(tmp_path)
    lines_changed = update_history(history, OLD_PATH, NEW_PATH)
    assert lines_changed == 2

    content = history.read_text()
    assert OLD_PATH not in content
    data = [json.loads(l) for l in content.splitlines() if l.strip()]
    assert data[0]["project"] == NEW_PATH
    assert data[1]["project"] == "/other/project"  # untouched
    assert data[2]["project"] == NEW_PATH


def test_update_history_dry_run(tmp_path):
    history = make_history(tmp_path)
    original = history.read_text()
    update_history(history, OLD_PATH, NEW_PATH, dry_run=True)
    assert history.read_text() == original


def test_update_history_missing_file(tmp_path):
    count = update_history(tmp_path / "nonexistent.jsonl", OLD_PATH, NEW_PATH)
    assert count == 0


# ─── Edge-case tests for _replace_in_file (A1 substring safety) ──────────

from claudepath.updaters import replace_in_file, merge_sessions_index


def test_replace_in_file_substring_safe(tmp_path):
    """old=/tmp/foo should NOT modify /tmp/foobar in the same JSON line."""
    f = tmp_path / "test.jsonl"
    f.write_text(
        json.dumps({"cwd": "/tmp/foo", "other": "/tmp/foobar/file"}) + "\n"
    )
    changed = replace_in_file(f, "/tmp/foo", "/tmp/bar", dry_run=False)
    assert changed == 1
    obj = json.loads(f.read_text().strip())
    assert obj["cwd"] == "/tmp/bar"
    assert obj["other"] == "/tmp/foobar/file"  # must NOT be touched


def test_replace_in_file_prefix_match(tmp_path):
    """old=/tmp/foo SHOULD modify /tmp/foo/subdir (prefix + slash)."""
    f = tmp_path / "test.jsonl"
    f.write_text(json.dumps({"cwd": "/tmp/foo/subdir"}) + "\n")
    changed = replace_in_file(f, "/tmp/foo", "/tmp/bar", dry_run=False)
    assert changed == 1
    obj = json.loads(f.read_text().strip())
    assert obj["cwd"] == "/tmp/bar/subdir"


def test_replace_in_file_malformed_json_line(tmp_path):
    """Non-JSON lines fall back to naive string replace."""
    f = tmp_path / "test.jsonl"
    f.write_text("this line mentions /tmp/foo somewhere\n")
    changed = replace_in_file(f, "/tmp/foo", "/tmp/bar", dry_run=False)
    assert changed == 1
    assert f.read_text() == "this line mentions /tmp/bar somewhere\n"


def test_replace_in_file_empty_file(tmp_path):
    """Empty file returns 0 changes."""
    f = tmp_path / "test.jsonl"
    f.write_text("")
    changed = replace_in_file(f, "/tmp/foo", "/tmp/bar", dry_run=False)
    assert changed == 0


def test_replace_in_file_no_trailing_newline(tmp_path):
    """File without trailing newline still works correctly."""
    f = tmp_path / "test.jsonl"
    f.write_text(json.dumps({"cwd": "/tmp/foo"}))  # no trailing newline
    changed = replace_in_file(f, "/tmp/foo", "/tmp/bar", dry_run=False)
    assert changed == 1
    obj = json.loads(f.read_text().strip())
    assert obj["cwd"] == "/tmp/bar"


def test_replace_in_file_unicode_paths(tmp_path):
    """Paths with unicode characters work correctly."""
    f = tmp_path / "test.jsonl"
    f.write_text(json.dumps({"cwd": "/home/用户/项目"}, ensure_ascii=False) + "\n")
    changed = replace_in_file(f, "/home/用户/项目", "/home/user/project", dry_run=False)
    assert changed == 1
    obj = json.loads(f.read_text().strip())
    assert obj["cwd"] == "/home/user/project"


def test_replace_in_file_path_in_content_field(tmp_path):
    """Paths inside deeply nested message content strings are also replaced."""
    f = tmp_path / "test.jsonl"
    line = json.dumps({
        "type": "assistant",
        "message": {
            "content": [
                {"type": "text", "text": "I edited /tmp/foo/src/main.py"},
                {"type": "tool_use", "input": {"path": "/tmp/foo/src/main.py"}},
            ]
        },
    })
    f.write_text(line + "\n")
    changed = replace_in_file(f, "/tmp/foo", "/tmp/bar", dry_run=False)
    assert changed == 1
    obj = json.loads(f.read_text().strip())
    # The tool_use input path (exact/prefix match) should be replaced
    assert obj["message"]["content"][1]["input"]["path"] == "/tmp/bar/src/main.py"


# ─── Merge warning (A4) ──────────────────────────────────────────────────

def test_merge_duplicate_session_id_warning(tmp_path, capsys):
    """Verify warning is printed to stderr when duplicate sessionId found during merge."""
    session_id = "dup-session-001"
    dst_data = {
        "version": 1,
        "originalPath": NEW_PATH,
        "entries": [
            {
                "sessionId": session_id,
                "projectPath": NEW_PATH,
                "fullPath": f"{CLAUDE_DIR}/projects/{NEW_ENCODED}/{session_id}.jsonl",
                "firstPrompt": "hello",
                "summary": "existing",
                "messageCount": 3,
                "created": "2026-01-01T00:00:00.000Z",
                "modified": "2026-01-02T00:00:00.000Z",
                "gitBranch": "",
                "isSidechain": False,
            }
        ],
    }
    src_data = {
        "version": 1,
        "originalPath": OLD_PATH,
        "entries": [
            {
                "sessionId": session_id,
                "projectPath": OLD_PATH,
                "fullPath": f"{CLAUDE_DIR}/projects/{OLD_ENCODED}/{session_id}.jsonl",
                "firstPrompt": "hi",
                "summary": "duplicate",
                "messageCount": 2,
                "created": "2026-01-03T00:00:00.000Z",
                "modified": "2026-01-04T00:00:00.000Z",
                "gitBranch": "",
                "isSidechain": False,
            }
        ],
    }
    dst_index = tmp_path / "dst-sessions-index.json"
    src_index = tmp_path / "src-sessions-index.json"
    dst_index.write_text(json.dumps(dst_data, indent=2))
    src_index.write_text(json.dumps(src_data, indent=2))

    merged = merge_sessions_index(
        dst_index, src_index, OLD_PATH, NEW_PATH, NEW_ENCODED
    )
    assert merged == 0  # duplicate was skipped

    captured = capsys.readouterr()
    assert "duplicate" in captured.err.lower() or "skipping" in captured.err.lower()
    assert session_id in captured.err
