"""
Tests for the backup module: create_backup, restore_backup, find_latest_backup,
and list_backups.
"""

import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from claudepath.backup import (
    create_backup,
    find_latest_backup,
    list_backups,
    restore_backup,
)


def _make_project_dir(tmp_path: Path) -> Path:
    """Create a minimal project directory with some files."""
    project_dir = tmp_path / "projects" / "-tmp-myproject"
    project_dir.mkdir(parents=True)
    (project_dir / "sessions-index.json").write_text(
        json.dumps({"version": 1, "originalPath": "/tmp/myproject"})
    )
    (project_dir / "sess-001.jsonl").write_text(
        json.dumps({"type": "user", "cwd": "/tmp/myproject"}) + "\n"
    )
    return project_dir


def _make_history(tmp_path: Path) -> Path:
    """Create a minimal history.jsonl."""
    history = tmp_path / "history.jsonl"
    history.write_text(
        json.dumps({"display": "cmd", "project": "/tmp/myproject", "timestamp": 1000}) + "\n"
    )
    return history


@pytest.fixture()
def backup_env(tmp_path):
    """Create project dir, history, and a backup. Returns a dict with all paths."""
    project_dir = _make_project_dir(tmp_path)
    history = _make_history(tmp_path)
    backup_base = tmp_path / "backups"
    backup_dir = create_backup(project_dir, history, backup_base)
    return {
        "tmp_path": tmp_path,
        "project_dir": project_dir,
        "history": history,
        "backup_base": backup_base,
        "backup_dir": backup_dir,
    }


# ─── create_backup ────────────────────────────────────────────────────────


def test_create_backup_copies_project_dir(backup_env):
    project_dir = backup_env["project_dir"]
    backup_dir = backup_env["backup_dir"]

    backed_up = backup_dir / "project_dir"
    assert backed_up.exists()
    assert (backed_up / "sessions-index.json").exists()
    assert (backed_up / "sess-001.jsonl").exists()
    # Content should match
    original = json.loads((project_dir / "sessions-index.json").read_text())
    restored = json.loads((backed_up / "sessions-index.json").read_text())
    assert original == restored


def test_create_backup_copies_history(backup_env):
    backup_dir = backup_env["backup_dir"]
    history = backup_env["history"]

    backed_up_history = backup_dir / "history.jsonl"
    assert backed_up_history.exists()
    assert backed_up_history.read_text() == history.read_text()


def test_create_backup_writes_manifest(backup_env):
    project_dir = backup_env["project_dir"]
    history = backup_env["history"]
    backup_dir = backup_env["backup_dir"]

    manifest = backup_dir / "manifest.txt"
    assert manifest.exists()
    content = manifest.read_text()
    assert f"project_dir={project_dir}" in content
    assert f"history_path={history}" in content
    # No merge_target_dir line when extra_dir is not provided
    assert "merge_target_dir" not in content


def test_create_backup_with_extra_dir(tmp_path):
    project_dir = _make_project_dir(tmp_path)
    history = _make_history(tmp_path)
    backup_base = tmp_path / "backups"

    extra_dir = tmp_path / "projects" / "-tmp-other"
    extra_dir.mkdir(parents=True)
    (extra_dir / "sess-new.jsonl").write_text(
        json.dumps({"type": "user", "cwd": "/tmp/other"}) + "\n"
    )

    backup_dir = create_backup(project_dir, history, backup_base, extra_dir=extra_dir)

    assert (backup_dir / "merge_target_dir").exists()
    assert (backup_dir / "merge_target_dir" / "sess-new.jsonl").exists()
    # Manifest should include merge_target_dir
    manifest_content = (backup_dir / "manifest.txt").read_text()
    assert f"merge_target_dir={extra_dir}" in manifest_content


def test_create_backup_missing_project_dir(tmp_path):
    nonexistent = tmp_path / "does-not-exist"
    history = _make_history(tmp_path)
    backup_base = tmp_path / "backups"

    backup_dir = create_backup(nonexistent, history, backup_base)

    # Backup dir is created but has no project_dir inside
    assert backup_dir.exists()
    assert not (backup_dir / "project_dir").exists()
    # History and manifest are still backed up
    assert (backup_dir / "history.jsonl").exists()
    assert (backup_dir / "manifest.txt").exists()


# ─── restore_backup ──────────────────────────────────────────────────────


def test_restore_backup_restores_project_dir(backup_env):
    project_dir = backup_env["project_dir"]
    backup_dir = backup_env["backup_dir"]

    # Simulate a destructive operation: remove the project dir
    shutil.rmtree(project_dir)
    assert not project_dir.exists()

    result = restore_backup(backup_dir)

    assert result is True
    assert project_dir.exists()
    assert (project_dir / "sessions-index.json").exists()
    assert (project_dir / "sess-001.jsonl").exists()


def test_restore_backup_restores_history(backup_env):
    history = backup_env["history"]
    backup_dir = backup_env["backup_dir"]
    original_content = history.read_text()

    # Corrupt the history file
    history.write_text("corrupted\n")

    result = restore_backup(backup_dir)

    assert result is True
    assert history.read_text() == original_content


def test_restore_backup_missing_manifest(tmp_path):
    # Create a backup dir without a manifest
    fake_backup = tmp_path / "backups" / "20260101_000000"
    fake_backup.mkdir(parents=True)

    result = restore_backup(fake_backup)

    assert result is False


def test_restore_backup_atomic_preserves_on_failure(backup_env):
    project_dir = backup_env["project_dir"]
    backup_dir = backup_env["backup_dir"]

    # Modify the project dir so we can verify it's preserved on failure
    (project_dir / "new-file.txt").write_text("important data")

    # Patch shutil.copytree to fail during restore
    original_copytree = shutil.copytree

    def failing_copytree(src, dst, *args, **kwargs):
        # Let other copytree calls through, only fail when restoring project_dir
        if str(dst) == str(project_dir):
            raise OSError("Simulated copy failure")
        return original_copytree(src, dst, *args, **kwargs)

    with patch("claudepath.backup.shutil.copytree", side_effect=failing_copytree):
        result = restore_backup(backup_dir)

    assert result is False
    # The original project dir should be preserved (renamed back)
    assert project_dir.exists()
    assert (project_dir / "new-file.txt").exists()
    assert (project_dir / "new-file.txt").read_text() == "important data"


# ─── find_latest_backup ──────────────────────────────────────────────────


def test_find_latest_backup(tmp_path):
    backup_base = tmp_path / "backups"
    # Create several backup dirs with different timestamps
    (backup_base / "20260101_100000").mkdir(parents=True)
    (backup_base / "20260215_143000").mkdir(parents=True)
    (backup_base / "20260227_090000").mkdir(parents=True)

    result = find_latest_backup(backup_base)

    assert result is not None
    assert result.name == "20260227_090000"


def test_find_latest_backup_empty(tmp_path):
    backup_base = tmp_path / "backups"
    backup_base.mkdir(parents=True)

    result = find_latest_backup(backup_base)

    assert result is None


def test_find_latest_backup_no_dir(tmp_path):
    backup_base = tmp_path / "backups" / "nonexistent"

    result = find_latest_backup(backup_base)

    assert result is None


# ─── list_backups ─────────────────────────────────────────────────────────


def test_list_backups_returns_metadata(tmp_path):
    backup_base = tmp_path / "backups"
    bd = backup_base / "20260227_120000"
    bd.mkdir(parents=True)
    manifest = bd / "manifest.txt"
    manifest.write_text(
        "project_dir=/home/user/myproject\n"
        "history_path=/home/user/.claude/history.jsonl\n"
        "merge_target_dir=/home/user/.claude/projects/-other\n"
    )

    results = list_backups(backup_base)

    assert len(results) == 1
    entry = results[0]
    assert entry["timestamp"] == "20260227_120000"
    assert entry["path"] == bd
    assert entry["project_dir"] == "/home/user/myproject"
    assert entry["has_merge_target"] is True


def test_list_backups_empty(tmp_path):
    backup_base = tmp_path / "backups"
    backup_base.mkdir(parents=True)

    results = list_backups(backup_base)

    assert results == []


def test_list_backups_sorted_newest_first(tmp_path):
    backup_base = tmp_path / "backups"
    for ts in ["20260101_100000", "20260227_090000", "20260215_143000"]:
        bd = backup_base / ts
        bd.mkdir(parents=True)
        (bd / "manifest.txt").write_text(f"project_dir=/proj/{ts}\nhistory_path=/h.jsonl\n")

    results = list_backups(backup_base)

    assert len(results) == 3
    timestamps = [r["timestamp"] for r in results]
    assert timestamps == ["20260227_090000", "20260215_143000", "20260101_100000"]


# ─── atomic restore behavior (via restore_backup) ───────────────────────


def test_restore_replaces_existing_project_dir(backup_env):
    """Restore overwrites modified project dir with backup contents."""
    project_dir = backup_env["project_dir"]
    backup_dir = backup_env["backup_dir"]

    # Modify the project dir after backup
    (project_dir / "extra.txt").write_text("post-backup change")
    (project_dir / "sess-001.jsonl").write_text("corrupted\n")

    result = restore_backup(backup_dir)

    assert result is True
    assert project_dir.exists()
    # Original content restored
    assert (project_dir / "sess-001.jsonl").read_text().strip() != "corrupted"
    # Post-backup file should not be present (entire dir replaced)
    assert not (project_dir / "extra.txt").exists()
    # No stale temp dir left behind
    temp_old = project_dir.with_name(project_dir.name + ".claudepath-old")
    assert not temp_old.exists()


