"""
CLI entry point for claudepath.
"""

import difflib
import os
import subprocess
import sys
import threading
import urllib.error
import urllib.request
import json as _json
from pathlib import Path
from typing import Callable, Optional

from claudepath import __version__
from claudepath.mover import MoveError, move_project, preview_operation, remap_project
from claudepath.scanner import find_claude_dir, list_projects
from claudepath.backup import (
    find_latest_backup,
    get_backup_base,
    list_backups,
    restore_backup,
)

# ANSI color codes (no external dependencies)
RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"
DIM = "\033[2m"

ALL_COMMANDS = ["mv", "remap", "list", "update", "restore", "help"]


def supports_color() -> bool:
    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("FORCE_COLOR") is not None:
        return True
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _c(text: str, *codes: str) -> str:
    if not supports_color():
        return text
    return "".join(codes) + text + RESET


# ─── Help ──────────────────────────────────────────────────────────────────

def print_help() -> None:
    print(
        f"""
{_c("claudepath", BOLD, CYAN)} {_c(f"v{__version__}", DIM)} — Move Claude Code projects without losing session history

{_c("USAGE", BOLD)}
  claudepath <command> [options]

{_c("COMMANDS", BOLD)}
  {_c("mv", BOLD)} <old-path> <new-path>      Move project directory and update all Claude references
  {_c("remap", BOLD)} <old-path> <new-path>   Update Claude references only (directory already moved)
  {_c("list", BOLD)}                          List all projects tracked by Claude Code
  {_c("update", BOLD)}                        Update claudepath to the latest version
  {_c("restore", BOLD)}                       Restore from a previous backup
  {_c("help", BOLD)}                          Show this help message

{_c("OPTIONS (mv / remap)", BOLD)}
  --dry-run        Preview changes without modifying any files
  --no-backup      Skip creating a backup before modifying files
  --yes            Skip interactive confirmation prompt
  --merge          Merge sessions when destination already has Claude data
  --verbose, -v    Show detailed output of each file processed
  --claude-dir     Override the Claude data directory (default: ~/.claude)

{_c("EXAMPLES", BOLD)}
  # Move a project to a new location
  claudepath mv ~/projects/old-name ~/projects/new-name

  # You already moved the directory manually — just update Claude's references
  claudepath remap ~/old/path ~/new/path

  # Preview what would change without touching anything
  claudepath mv ~/projects/old ~/projects/new --dry-run

  # List all Claude Code projects
  claudepath list

  # Restore from the latest backup
  claudepath restore

{_c("WHAT IT UPDATES", BOLD)}
  - ~/.claude/projects/{{encoded-dir}}/     (renamed)
  - ~/.claude/projects/.../sessions-index.json
  - ~/.claude/projects/.../{{session}}.jsonl  (all sessions, recursively)
  - ~/.claude/history.jsonl

{_c("BACKUP", BOLD)}
  By default, a backup is created before any changes in:
  ~/.claude/backups/claudepath/{{timestamp}}/
  Use --no-backup to skip (only if you have your own backup).

{_c("REPORT ISSUES", BOLD)}
  https://github.com/Mahiler1909/claudepath/issues
"""
    )


def _print_help_mv() -> None:
    print(f"""\
{_c("claudepath mv", BOLD)} — Move project directory and update Claude references

{_c("USAGE", BOLD)}
  claudepath mv <old-path> <new-path> [options]

{_c("OPTIONS", BOLD)}
  --dry-run        Preview changes without modifying any files
  --no-backup      Skip creating a backup before modifying files
  --yes, -y        Skip interactive confirmation prompt
  --merge          Merge sessions when destination already has Claude data
  --verbose, -v    Show detailed output of each file processed
  --claude-dir     Override the Claude data directory (default: ~/.claude)

{_c("EXAMPLES", BOLD)}
  claudepath mv ~/projects/old-name ~/projects/new-name
  claudepath mv ~/projects/old ~/projects/new --dry-run
  claudepath mv ~/old ~/new --merge --yes
""")


def _print_help_remap() -> None:
    print(f"""\
{_c("claudepath remap", BOLD)} — Update Claude references only (directory already moved)

{_c("USAGE", BOLD)}
  claudepath remap <old-path> <new-path> [options]

{_c("OPTIONS", BOLD)}
  --dry-run        Preview changes without modifying any files
  --no-backup      Skip creating a backup before modifying files
  --yes, -y        Skip interactive confirmation prompt
  --merge          Merge sessions when destination already has Claude data
  --verbose, -v    Show detailed output of each file processed
  --claude-dir     Override the Claude data directory (default: ~/.claude)

{_c("EXAMPLES", BOLD)}
  claudepath remap ~/old/path ~/new/path
  claudepath remap ~/old ~/new --merge
""")


def _print_help_list() -> None:
    print(f"""\
{_c("claudepath list", BOLD)} — List all projects tracked by Claude Code

{_c("USAGE", BOLD)}
  claudepath list [options]

{_c("OPTIONS", BOLD)}
  --claude-dir     Override the Claude data directory (default: ~/.claude)
""")


def _print_help_update() -> None:
    print(f"""\
{_c("claudepath update", BOLD)} — Update claudepath to the latest version

{_c("USAGE", BOLD)}
  claudepath update [options]

{_c("OPTIONS", BOLD)}
  --brew           Force update via Homebrew
  --pipx           Force update via pipx
  --pip            Force update via pip

Auto-detects the install method if no override is given.
""")


def _print_help_restore() -> None:
    print(f"""\
{_c("claudepath restore", BOLD)} — Restore from a previous backup

{_c("USAGE", BOLD)}
  claudepath restore [<timestamp>] [options]

{_c("OPTIONS", BOLD)}
  --list           List all available backups
  --claude-dir     Override the Claude data directory (default: ~/.claude)

{_c("EXAMPLES", BOLD)}
  claudepath restore              # restore latest backup
  claudepath restore --list       # list all backups
  claudepath restore 20260227_145300  # restore a specific backup
""")


_HELP_MAP = {
    "mv": _print_help_mv,
    "remap": _print_help_remap,
    "list": _print_help_list,
    "update": _print_help_update,
    "restore": _print_help_restore,
}


# ─── Utilities ─────────────────────────────────────────────────────────────

def confirm(prompt: str) -> bool:
    """Ask for user confirmation. Returns True if user confirms."""
    try:
        answer = input(f"{prompt} [y/N] ").strip().lower()
        return answer in ("y", "yes")
    except (KeyboardInterrupt, EOFError):
        print()
        return False


def print_error(msg: str) -> None:
    print(_c(f"Error: {msg}", RED), file=sys.stderr)


def _check_claude_running(project_path: str) -> bool:
    """Check if Claude Code might be using this project."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", f"claude.*{project_path}"],
            capture_output=True, timeout=2,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


# ─── Argument Parsing ──────────────────────────────────────────────────────

def parse_mv_remap_args(args: list, cmd_name: str = "mv") -> dict:
    """Parse arguments for mv and remap subcommands."""
    if "--help" in args or "-h" in args:
        fn = _HELP_MAP.get(cmd_name)
        if fn:
            fn()
        sys.exit(0)

    opts = {
        "old_path": None,
        "new_path": None,
        "dry_run": False,
        "no_backup": False,
        "yes": False,
        "merge": False,
        "verbose": False,
        "claude_dir": None,
    }

    positional = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--dry-run":
            opts["dry_run"] = True
        elif arg == "--no-backup":
            opts["no_backup"] = True
        elif arg in ("--yes", "-y"):
            opts["yes"] = True
        elif arg == "--merge":
            opts["merge"] = True
        elif arg in ("--verbose", "-v"):
            opts["verbose"] = True
        elif arg == "--claude-dir":
            i += 1
            if i >= len(args):
                print_error("--claude-dir requires a value")
                sys.exit(1)
            opts["claude_dir"] = args[i]
        elif arg.startswith("--"):
            print_error(f"Unknown option: {arg}")
            sys.exit(1)
        else:
            positional.append(arg)
        i += 1

    if len(positional) < 2:
        print_error("Both <old-path> and <new-path> are required.")
        print(f"\n  Usage: claudepath {cmd_name} <old-path> <new-path> [options]", file=sys.stderr)
        print(f"  Run 'claudepath {cmd_name} --help' for details.", file=sys.stderr)
        sys.exit(1)

    opts["old_path"] = positional[0]
    opts["new_path"] = positional[1]
    return opts


# ─── Commands ──────────────────────────────────────────────────────────────

def _run_operation(args: list, cmd_name: str, confirm_prompt: str, from_label: str, operation: Callable) -> None:
    opts = parse_mv_remap_args(args, cmd_name=cmd_name)
    old_path = str(Path(opts["old_path"]).expanduser().resolve())
    new_path = str(Path(opts["new_path"]).expanduser().resolve())
    claude_dir = Path(opts["claude_dir"]).expanduser() if opts["claude_dir"] else None
    dry_run = opts["dry_run"]
    no_backup = opts["no_backup"]
    merge = opts["merge"]
    verbose = opts["verbose"]

    if dry_run:
        print(_c("DRY RUN — no files will be modified", YELLOW, BOLD))
        print()

    print(f"  {_c(from_label, BOLD)} {old_path}")
    print(f"  {_c('To:  ', BOLD)} {new_path}")
    print()

    # Show preview of what will change
    if not dry_run and not opts["yes"]:
        preview = preview_operation(old_path, claude_dir=claude_dir)
        if preview["project_found"]:
            print(f"  {_c('Will update:', DIM)}")
            print(f"    - Project directory (rename)")
            if preview["session_count"]:
                print(f"    - {preview['session_count']} session file(s)")
            if preview["has_history"]:
                print(f"    - history.jsonl")
            if not no_backup:
                print(f"    - Backup will be created")
        else:
            print(f"  {_c('Warning:', YELLOW)} Project not found in Claude data.")
            print(f"  Tip: run 'claudepath list' to see tracked projects.")
        print()

        # Check if Claude Code is running
        if _check_claude_running(old_path):
            print(
                _c("  Warning: Claude Code may be using this project.", YELLOW, BOLD)
            )
            print("  Close it first to avoid data corruption.\n")

        if not confirm(confirm_prompt):
            print("Aborted.")
            sys.exit(0)

    try:
        result = operation(
            old_path, new_path, claude_dir=claude_dir, dry_run=dry_run,
            no_backup=no_backup, merge=merge, verbose=verbose,
        )
        print(_c("Done!", GREEN, BOLD))
        print(result.summary())
    except MoveError as e:
        print_error(str(e))
        sys.exit(1)


def cmd_mv(args: list) -> None:
    _run_operation(
        args,
        cmd_name="mv",
        confirm_prompt="Move project and update all Claude Code references?",
        from_label="From:",
        operation=move_project,
    )


def cmd_remap(args: list) -> None:
    _run_operation(
        args,
        cmd_name="remap",
        confirm_prompt="Update all Claude Code references to the new path?",
        from_label="Old: ",
        operation=remap_project,
    )


def cmd_list(args: list) -> None:
    if "--help" in args or "-h" in args:
        _print_help_list()
        return

    claude_dir = find_claude_dir()
    for arg in args:
        if arg == "--claude-dir" and args:
            idx = args.index("--claude-dir")
            if idx + 1 < len(args):
                claude_dir = Path(args[idx + 1]).expanduser()

    projects = list_projects(claude_dir)
    if not projects:
        print("No Claude Code projects found.")
        return

    print(_c(f"Claude Code projects in {claude_dir}/projects/\n", BOLD))
    for p in projects:
        path = p["project_path"]
        sessions = p["session_count"]
        modified = p["last_modified"] or "unknown"
        # Trim the modified timestamp to date+time for readability
        if "T" in modified:
            modified = modified[:16].replace("T", " ")

        exists = Path(path).exists() if path else False
        status = _c(" ✓", GREEN) if exists else _c(" ✗ orphaned", RED, DIM)
        print(f"  {_c(path, BOLD)}{status}")
        print(f"    {_c('sessions:', DIM)} {sessions}  {_c('last active:', DIM)} {modified}")
        print()


def cmd_restore(args: list) -> None:
    if "--help" in args or "-h" in args:
        _print_help_restore()
        return

    claude_dir = find_claude_dir()
    show_list = False
    timestamp = None

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--list":
            show_list = True
        elif arg == "--claude-dir":
            i += 1
            if i < len(args):
                claude_dir = Path(args[i]).expanduser()
        elif not arg.startswith("--"):
            timestamp = arg
        i += 1

    backup_base = get_backup_base(claude_dir)

    if show_list:
        backups = list_backups(backup_base)
        if not backups:
            print("No backups found.")
            return
        print(_c(f"Available backups in {backup_base}/\n", BOLD))
        for b in backups:
            merge_tag = _c(" (merge)", DIM) if b["has_merge_target"] else ""
            print(f"  {_c(b['timestamp'], BOLD)}{merge_tag}")
            if b["project_dir"]:
                print(f"    {_c('project:', DIM)} {b['project_dir']}")
            print()
        return

    # Find the backup to restore
    if timestamp:
        backup_dir = backup_base / timestamp
        if not backup_dir.exists():
            print_error(f"Backup not found: {timestamp}")
            print("Run 'claudepath restore --list' to see available backups.", file=sys.stderr)
            sys.exit(1)
    else:
        backup_dir = find_latest_backup(backup_base)
        if not backup_dir:
            print_error("No backups found.")
            print("Backups are created automatically when running 'mv' or 'remap'.", file=sys.stderr)
            sys.exit(1)

    print(f"  {_c('Backup:', BOLD)} {backup_dir.name}")

    # Show manifest info
    manifest = backup_dir / "manifest.txt"
    if manifest.exists():
        for line in manifest.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                print(f"    {_c(k.strip() + ':', DIM)} {v.strip()}")
    print()

    if not confirm("Restore from this backup?"):
        print("Aborted.")
        return

    success = restore_backup(backup_dir)
    if success:
        print(_c("Restored successfully!", GREEN, BOLD))
    else:
        print_error("Restore completed with errors. Some files may not have been restored.")
        sys.exit(1)


# ─── Update ────────────────────────────────────────────────────────────────

def detect_install_method() -> str:
    """Detect how claudepath was installed. Returns 'brew', 'pipx', or 'pip'."""
    pkg_path = os.path.realpath(__file__).lower()
    if "/homebrew/" in pkg_path or "/cellar/" in pkg_path:
        return "brew"
    if "/pipx/" in pkg_path:
        return "pipx"
    return "pip"


def cmd_update(args: list) -> None:
    if "--help" in args or "-h" in args:
        _print_help_update()
        return

    # Parse flags
    method_override = None
    for arg in args:
        if arg == "--brew":
            method_override = "brew"
        elif arg == "--pipx":
            method_override = "pipx"
        elif arg == "--pip":
            method_override = "pip"
        elif arg.startswith("--"):
            print_error(f"Unknown option: {arg}")
            sys.exit(1)

    print(f"  {_c('Current version:', BOLD)} {__version__}")
    print(f"  Checking for updates...")

    latest = check_latest_version()
    if latest is None:
        print_error("Could not check for updates. Check your internet connection.")
        sys.exit(1)

    if parse_version(latest) <= parse_version(__version__):
        print(f"\n  {_c('Already up to date!', GREEN, BOLD)}")
        return

    method = method_override or detect_install_method()

    print(f"  {_c('New version:', BOLD)} {latest}")
    print(f"  {_c('Install method:', BOLD)} {method}")
    print()

    if method == "brew":
        cmd = ["brew", "upgrade", "claudepath"]
    elif method == "pipx":
        cmd = ["pipx", "upgrade", "claudepath"]
    else:
        cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "claudepath"]

    print(f"  {_c('Running:', DIM)} {' '.join(cmd)}\n")
    result = subprocess.run(cmd)

    if result.returncode == 0:
        print(f"\n  {_c(f'Updated to v{latest}!', GREEN, BOLD)}")
    else:
        print_error(f"Update failed (exit code {result.returncode})")
        sys.exit(1)


# ─── Version Check ─────────────────────────────────────────────────────────


def parse_version(version: str) -> tuple:
    """Parse a version string like '1.2.3' into a tuple of ints for comparison."""
    return tuple(int(x) for x in version.split("."))


def check_latest_version() -> Optional[str]:
    """Fetch the latest version from PyPI. Returns version string or None on failure."""
    try:
        req = urllib.request.Request(
            "https://pypi.org/pypi/claudepath/json",
            headers={"User-Agent": f"claudepath/{__version__}"},
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = _json.loads(resp.read())
            return data["info"]["version"]
    except (OSError, urllib.error.URLError, ValueError, KeyError):
        return None


def _print_update_notice(latest: str) -> None:
    print(
        f"\n{_c('⚠', YELLOW, BOLD)}  {_c(f'New version available: {latest}', YELLOW)} "
        f"{_c(f'(you have {__version__})', DIM)}"
    )
    print(f"   {_c('claudepath update', BOLD)}  {_c('# update automatically', DIM)}")


# ─── Main ──────────────────────────────────────────────────────────────────

def main() -> None:
    args = sys.argv[1:]

    if not args or args[0] in ("help", "--help", "-h"):
        print_help()
        return

    if args[0] == "--version":
        print(f"claudepath {__version__}")
        return

    command = args[0]
    rest = args[1:]

    # update and restore handle their own flow — skip background check
    if command == "update":
        cmd_update(rest)
        return
    if command == "restore":
        cmd_restore(rest)
        return

    # Check for updates in background — does not block command execution
    latest_version: list = []
    checker = threading.Thread(
        target=lambda: latest_version.append(check_latest_version()),
        daemon=True,
    )
    checker.start()

    if command == "mv":
        cmd_mv(rest)
    elif command == "remap":
        cmd_remap(rest)
    elif command == "list":
        cmd_list(rest)
    else:
        matches = difflib.get_close_matches(command, ALL_COMMANDS, n=1, cutoff=0.6)
        if matches:
            print_error(f"Unknown command: '{command}'. Did you mean '{matches[0]}'?")
        else:
            print_error(f"Unknown command: '{command}'")
        print("Run 'claudepath help' for usage.", file=sys.stderr)
        sys.exit(1)

    # Wait up to 2s for the version check, then print notice if outdated
    checker.join(timeout=2)
    if (latest_version and latest_version[0]
            and parse_version(latest_version[0]) > parse_version(__version__)):
        _print_update_notice(latest_version[0])


if __name__ == "__main__":
    main()
