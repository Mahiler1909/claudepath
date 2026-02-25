"""
Backup and rollback utilities for claudepath.

Before modifying any Claude Code data files, a backup is created.
If any step fails, the backup can be restored automatically.

Backups are stored in: ~/.claude/backups/claudepath/{timestamp}/
"""

import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional


def create_backup(
    project_dir: Path,
    history_path: Path,
    backup_base: Path,
) -> Path:
    """Create a backup of the project directory and history.jsonl.

    Args:
        project_dir: The ~/.claude/projects/{encoded}/ directory to back up.
        history_path: The ~/.claude/history.jsonl file to back up.
        backup_base: Base directory for backups (~/.claude/backups/claudepath/).

    Returns:
        Path to the created backup directory.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = backup_base / timestamp
    backup_dir.mkdir(parents=True, exist_ok=True)

    # Back up the project directory
    if project_dir.exists():
        dest = backup_dir / "project_dir"
        shutil.copytree(str(project_dir), str(dest))

    # Back up history.jsonl
    if history_path.exists():
        shutil.copy2(str(history_path), str(backup_dir / "history.jsonl"))

    # Write a manifest so restore knows what to put back where
    manifest = backup_dir / "manifest.txt"
    manifest.write_text(
        f"project_dir={project_dir}\nhistory_path={history_path}\n",
        encoding="utf-8",
    )

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
