"""
CLI entry point for claudepath.
"""

import sys
import threading
import urllib.request
import json as _json
from pathlib import Path
from typing import Callable, Optional

from claudepath import __version__
from claudepath.mover import MoveError, move_project, remap_project
from claudepath.scanner import find_claude_dir, list_projects

# ANSI color codes (no external dependencies)
RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"
DIM = "\033[2m"


def _supports_color() -> bool:
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _c(text: str, *codes: str) -> str:
    if not _supports_color():
        return text
    return "".join(codes) + text + RESET


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
  {_c("help", BOLD)}                          Show this help message

{_c("OPTIONS (mv / remap)", BOLD)}
  --dry-run        Preview changes without modifying any files
  --no-backup      Skip creating a backup before modifying files
  --yes            Skip interactive confirmation prompt
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


def _confirm(prompt: str) -> bool:
    """Ask for user confirmation. Returns True if user confirms."""
    try:
        answer = input(f"{prompt} [y/N] ").strip().lower()
        return answer in ("y", "yes")
    except (KeyboardInterrupt, EOFError):
        print()
        return False


def _parse_mv_remap_args(args: list) -> dict:
    """Parse arguments for mv and remap subcommands."""
    opts = {
        "old_path": None,
        "new_path": None,
        "dry_run": False,
        "no_backup": False,
        "yes": False,
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
        sys.exit(1)

    opts["old_path"] = positional[0]
    opts["new_path"] = positional[1]
    return opts


def print_error(msg: str) -> None:
    print(_c(f"Error: {msg}", RED), file=sys.stderr)


def _run_operation(args: list, confirm_prompt: str, from_label: str, operation: Callable) -> None:
    opts = _parse_mv_remap_args(args)
    old_path = str(Path(opts["old_path"]).expanduser().resolve())
    new_path = str(Path(opts["new_path"]).expanduser().resolve())
    claude_dir = Path(opts["claude_dir"]).expanduser() if opts["claude_dir"] else None
    dry_run = opts["dry_run"]
    no_backup = opts["no_backup"]

    if dry_run:
        print(_c("DRY RUN — no files will be modified", YELLOW, BOLD))
        print()

    print(f"  {_c(from_label, BOLD)} {old_path}")
    print(f"  {_c('To:  ', BOLD)} {new_path}")
    print()

    if not dry_run and not opts["yes"]:
        if not _confirm(confirm_prompt):
            print("Aborted.")
            sys.exit(0)

    try:
        result = operation(old_path, new_path, claude_dir=claude_dir, dry_run=dry_run, no_backup=no_backup)
        print(_c("Done!", GREEN, BOLD))
        print(result.summary())
    except MoveError as e:
        print_error(str(e))
        sys.exit(1)


def cmd_mv(args: list) -> None:
    _run_operation(
        args,
        confirm_prompt="Move project and update all Claude Code references?",
        from_label="From:",
        operation=move_project,
    )


def cmd_remap(args: list) -> None:
    _run_operation(
        args,
        confirm_prompt="Update all Claude Code references to the new path?",
        from_label="Old: ",
        operation=remap_project,
    )


def cmd_list(args: list) -> None:
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
        print(f"  {_c(path, BOLD)}")
        print(f"    {_c('sessions:', DIM)} {sessions}  {_c('last active:', DIM)} {modified}")
        print()


def _check_latest_version() -> Optional[str]:
    """Fetch the latest version from PyPI. Returns version string or None on failure."""
    try:
        req = urllib.request.Request(
            "https://pypi.org/pypi/claudepath/json",
            headers={"User-Agent": f"claudepath/{__version__}"},
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = _json.loads(resp.read())
            return data["info"]["version"]
    except Exception:
        return None


def _print_update_notice(latest: str) -> None:
    print(
        f"\n{_c('⚠', YELLOW, BOLD)}  {_c(f'New version available: {latest}', YELLOW)} "
        f"{_c(f'(you have {__version__})', DIM)}"
    )
    print(f"   {_c('pipx upgrade claudepath', BOLD)}  {_c('# if installed via pipx', DIM)}")
    print(f"   {_c('brew upgrade claudepath', BOLD)}  {_c('# if installed via Homebrew', DIM)}")


def main() -> None:
    args = sys.argv[1:]

    if not args or args[0] in ("help", "--help", "-h"):
        print_help()
        return

    if args[0] == "--version":
        print(f"claudepath {__version__}")
        return

    # Check for updates in background — does not block command execution
    latest_version: list = []
    checker = threading.Thread(
        target=lambda: latest_version.append(_check_latest_version()),
        daemon=True,
    )
    checker.start()

    command = args[0]
    rest = args[1:]

    if command == "mv":
        cmd_mv(rest)
    elif command == "remap":
        cmd_remap(rest)
    elif command == "list":
        cmd_list(rest)
    else:
        print_error(f"Unknown command: '{command}'")
        print("Run 'claudepath help' for usage.", file=sys.stderr)
        sys.exit(1)

    # Wait up to 2s for the version check, then print notice if outdated
    checker.join(timeout=2)
    if latest_version and latest_version[0] and latest_version[0] != __version__:
        _print_update_notice(latest_version[0])


if __name__ == "__main__":
    main()
