"""
Backup and rollback utilities for claudepath.

Before modifying any Claude Code data files, a backup is created.
If any step fails, the backup can be restored automatically.

Backups are stored in: ~/.claude/backups/claudepath/{timestamp}/
"""

import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, Union


def create_backup(
    project_dir: Path,
    history_path: Path,
    backup_base: Path,
    extra_dir: Optional[Path] = None,
) -> Path:
    """Create a backup of the project directory and history.jsonl.

    Args:
        project_dir: The ~/.claude/projects/{encoded}/ directory to back up.
        history_path: The ~/.claude/history.jsonl file to back up.
        backup_base: Base directory for backups (~/.claude/backups/claudepath/).
        extra_dir: Optional second project dir to back up (used during --merge).

    Returns:
        Path to the created backup directory.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = backup_base / timestamp
    backup_dir.mkdir(parents=True, exist_ok=True)

    # Back up the source project directory
    if project_dir.exists():
        dest = backup_dir / "project_dir"
        shutil.copytree(str(project_dir), str(dest))

    # Back up the merge target directory (destination that already has data)
    if extra_dir is not None and extra_dir.exists():
        dest = backup_dir / "merge_target_dir"
        shutil.copytree(str(extra_dir), str(dest))

    # Back up history.jsonl
    if history_path.exists():
        shutil.copy2(str(history_path), str(backup_dir / "history.jsonl"))

    # Write a manifest so restore knows what to put back where
    manifest_lines = [
        f"project_dir={project_dir}",
        f"history_path={history_path}",
    ]
    if extra_dir is not None:
        manifest_lines.append(f"merge_target_dir={extra_dir}")
    manifest = backup_dir / "manifest.txt"
    manifest.write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")

    return backup_dir


def restore_backup(backup_dir: Path) -> bool:
    """Restore files from a backup directory created by create_backup().

    Reads the manifest to know where to restore each item.
    Returns True on success, False if anything went wrong.
    """
    manifest = backup_dir / "manifest.txt"
    if not manifest.exists():
        return False

    config = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            config[k.strip()] = v.strip()

    project_dir = Path(config.get("project_dir", ""))
    history_path = Path(config.get("history_path", ""))

    success = True

    # Restore project directory
    backup_project = backup_dir / "project_dir"
    if backup_project.exists() and project_dir:
        if project_dir.exists():
            shutil.rmtree(project_dir)
        try:
            shutil.copytree(str(backup_project), str(project_dir))
        except OSError:
            success = False

    # Restore merge target directory (if backed up during --merge)
    merge_target_dir = Path(config.get("merge_target_dir", ""))
    backup_merge_target = backup_dir / "merge_target_dir"
    if backup_merge_target.exists() and merge_target_dir and str(merge_target_dir) != ".":
        if merge_target_dir.exists():
            shutil.rmtree(merge_target_dir)
        try:
            shutil.copytree(str(backup_merge_target), str(merge_target_dir))
        except OSError:
            success = False

    # Restore history.jsonl
    backup_history = backup_dir / "history.jsonl"
    if backup_history.exists() and history_path:
        try:
            shutil.copy2(str(backup_history), str(history_path))
        except OSError:
            success = False

    return success


def get_backup_base(claude_dir: Path) -> Path:
    """Return the base directory for claudepath backups."""
    return claude_dir / "backups" / "claudepath"


def find_latest_backup(backup_base: Path) -> Optional[Path]:
    """Return the most recently created backup directory, or None."""
    if not backup_base.exists():
        return None
    backups = sorted(
        [d for d in backup_base.iterdir() if d.is_dir()],
        key=lambda d: d.name,
        reverse=True,
    )
    return backups[0] if backups else None
