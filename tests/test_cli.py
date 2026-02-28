"""
Tests for the claudepath CLI module.
"""

import sys

import pytest

from claudepath import __version__
from claudepath.cli import (
    parse_version,
    confirm,
    detect_install_method,
    parse_mv_remap_args,
    supports_color,
    cmd_list,
    cmd_restore,
    cmd_update,
    main,
)


# ─── Argument Parsing (parse_mv_remap_args) ──────────────────────────────


def test_parse_args_basic():
    opts = parse_mv_remap_args(["/old/path", "/new/path"])
    assert opts["old_path"] == "/old/path"
    assert opts["new_path"] == "/new/path"
    assert opts["dry_run"] is False
    assert opts["no_backup"] is False
    assert opts["yes"] is False
    assert opts["merge"] is False
    assert opts["verbose"] is False
    assert opts["claude_dir"] is None


def test_parse_args_dry_run():
    opts = parse_mv_remap_args(["/old", "/new", "--dry-run"])
    assert opts["dry_run"] is True


def test_parse_args_no_backup():
    opts = parse_mv_remap_args(["/old", "/new", "--no-backup"])
    assert opts["no_backup"] is True


def test_parse_args_yes():
    opts = parse_mv_remap_args(["--yes", "/old", "/new"])
    assert opts["yes"] is True

    opts2 = parse_mv_remap_args(["/old", "-y", "/new"])
    assert opts2["yes"] is True


def test_parse_args_merge():
    opts = parse_mv_remap_args(["/old", "/new", "--merge"])
    assert opts["merge"] is True


def test_parse_args_verbose():
    opts = parse_mv_remap_args(["/old", "/new", "--verbose"])
    assert opts["verbose"] is True

    opts2 = parse_mv_remap_args(["/old", "/new", "-v"])
    assert opts2["verbose"] is True


def test_parse_args_claude_dir():
    opts = parse_mv_remap_args(["/old", "/new", "--claude-dir", "/custom/.claude"])
    assert opts["claude_dir"] == "/custom/.claude"


def test_parse_args_claude_dir_missing_value():
    with pytest.raises(SystemExit) as exc_info:
        parse_mv_remap_args(["/old", "/new", "--claude-dir"])
    assert exc_info.value.code == 1


def test_parse_args_missing_paths(capsys):
    with pytest.raises(SystemExit) as exc_info:
        parse_mv_remap_args(["/only-one"])
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "old-path" in captured.err or "required" in captured.err.lower()


def test_parse_args_unknown_flag(capsys):
    with pytest.raises(SystemExit) as exc_info:
        parse_mv_remap_args(["/old", "/new", "--unknown-flag"])
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Unknown option" in captured.err


def test_parse_args_help_flag():
    with pytest.raises(SystemExit) as exc_info:
        parse_mv_remap_args(["--help"], cmd_name="mv")
    assert exc_info.value.code == 0


# ─── Main entry point ────────────────────────────────────────────────────


def test_main_help(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["claudepath", "help"])
    main()
    captured = capsys.readouterr()
    assert "claudepath" in captured.out
    assert "COMMANDS" in captured.out


def test_main_version(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["claudepath", "--version"])
    main()
    captured = capsys.readouterr()
    assert __version__ in captured.out


def test_main_unknown_command(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["claudepath", "xyz"])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Unknown command" in captured.err


def test_main_did_you_mean(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["claudepath", "mov"])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Did you mean" in captured.err
    assert "mv" in captured.err


# ─── Color support ───────────────────────────────────────────────────────


def test_supports_color_no_color_env(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    assert supports_color() is False


def test_supports_color_force_color_env(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("FORCE_COLOR", "1")
    assert supports_color() is True


# ─── Confirm ─────────────────────────────────────────────────────────────


def test_confirm_yes(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "y")
    assert confirm("Continue?") is True


def test_confirm_no(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "n")
    assert confirm("Continue?") is False


def test_confirm_eof(monkeypatch):
    def raise_eof(_):
        raise EOFError

    monkeypatch.setattr("builtins.input", raise_eof)
    assert confirm("Continue?") is False


# ─── Update command ──────────────────────────────────────────────────────


def test_detect_install_method_brew(monkeypatch):
    monkeypatch.setattr(
        "claudepath.cli.os.path.realpath",
        lambda _: "/opt/homebrew/lib/python3.11/site-packages/claudepath/cli.py",
    )
    assert detect_install_method() == "brew"


def test_detect_install_method_pipx(monkeypatch):
    monkeypatch.setattr(
        "claudepath.cli.os.path.realpath",
        lambda _: "/home/user/.local/pipx/venvs/claudepath/lib/python3.11/site-packages/claudepath/cli.py",
    )
    assert detect_install_method() == "pipx"


def test_detect_install_method_pip(monkeypatch):
    monkeypatch.setattr(
        "claudepath.cli.os.path.realpath",
        lambda _: "/home/user/.venv/lib/python3.11/site-packages/claudepath/cli.py",
    )
    assert detect_install_method() == "pip"


def test_cmd_update_already_up_to_date(monkeypatch, capsys):
    monkeypatch.setattr("claudepath.cli.check_latest_version", lambda: __version__)
    cmd_update([])
    captured = capsys.readouterr()
    assert "up to date" in captured.out.lower() or "Already" in captured.out


def test_cmd_update_network_error(monkeypatch, capsys):
    monkeypatch.setattr("claudepath.cli.check_latest_version", lambda: None)
    with pytest.raises(SystemExit) as exc_info:
        cmd_update([])
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "internet" in captured.err.lower() or "updates" in captured.err.lower()


def test_cmd_update_override_flags():
    """Verify --brew, --pipx, --pip are parsed without error."""
    # These don't trigger update because we're not mocking check_latest_version
    # We just test that the flag parsing doesn't raise unknown-option errors.
    # We need to mock check_latest_version to avoid network calls.
    # Instead, test that --brew doesn't cause "Unknown option" exit.
    # The simplest test: parse the flags and check no SystemExit(1).
    # cmd_update calls check_latest_version, so we must mock it.
    import unittest.mock as mock

    with mock.patch("claudepath.cli.check_latest_version", return_value=__version__):
        # These should all succeed without raising SystemExit
        cmd_update(["--brew"])
        cmd_update(["--pipx"])
        cmd_update(["--pip"])


def test_cmd_update_older_version_on_pypi(monkeypatch, capsys):
    """PyPI has an older version than local — should report up to date."""
    monkeypatch.setattr("claudepath.cli.check_latest_version", lambda: "0.4.0")
    cmd_update([])
    captured = capsys.readouterr()
    assert "up to date" in captured.out.lower() or "Already" in captured.out


# ─── Version comparison ──────────────────────────────────────────────────


def test_parse_version_basic():
    assert parse_version("1.0.0") == (1, 0, 0)
    assert parse_version("0.4.0") == (0, 4, 0)
    assert parse_version("10.20.30") == (10, 20, 30)


def test_parse_version_comparison():
    assert parse_version("1.0.0") > parse_version("0.4.0")
    assert parse_version("1.0.0") > parse_version("0.99.99")
    assert parse_version("1.0.1") > parse_version("1.0.0")
    assert parse_version("1.0.0") == parse_version("1.0.0")
    assert not parse_version("0.4.0") > parse_version("1.0.0")


# ─── Restore command ─────────────────────────────────────────────────────


def test_cmd_restore_list(tmp_path, monkeypatch, capsys):
    # Create a fake backup directory structure
    claude_dir = tmp_path / ".claude"
    backup_base = claude_dir / "backups" / "claudepath"
    backup_dir = backup_base / "20260227_120000"
    backup_dir.mkdir(parents=True)
    # Create a project_dir marker so list_backups picks it up
    (backup_dir / "project_dir").mkdir()

    monkeypatch.setattr("claudepath.cli.find_claude_dir", lambda: claude_dir)
    monkeypatch.setattr("claudepath.cli.get_backup_base", lambda cd: cd / "backups" / "claudepath")
    monkeypatch.setattr(
        "claudepath.cli.list_backups",
        lambda base: [
            {
                "timestamp": "20260227_120000",
                "project_dir": "some-project",
                "has_merge_target": False,
            }
        ],
    )

    cmd_restore(["--list"])
    captured = capsys.readouterr()
    assert "20260227_120000" in captured.out


def test_cmd_restore_no_backups(tmp_path, monkeypatch, capsys):
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True)

    monkeypatch.setattr("claudepath.cli.find_claude_dir", lambda: claude_dir)
    monkeypatch.setattr("claudepath.cli.get_backup_base", lambda cd: cd / "backups" / "claudepath")
    monkeypatch.setattr("claudepath.cli.find_latest_backup", lambda base: None)

    with pytest.raises(SystemExit) as exc_info:
        cmd_restore([])
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "No backups" in captured.err or "backups" in captured.err.lower()


# ─── List command ────────────────────────────────────────────────────────


def test_cmd_list_shows_orphaned_status(tmp_path, monkeypatch, capsys):
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True)

    # Create a project that points to a nonexistent path
    nonexistent_path = str(tmp_path / "nonexistent" / "project")

    monkeypatch.setattr("claudepath.cli.find_claude_dir", lambda: claude_dir)
    monkeypatch.setattr(
        "claudepath.cli.list_projects",
        lambda cd: [
            {
                "encoded_name": "fake-encoded",
                "project_path": nonexistent_path,
                "session_count": 2,
                "last_modified": "2026-01-15T10:30:00",
            }
        ],
    )
    # Disable color so we can check raw text
    monkeypatch.setenv("NO_COLOR", "1")

    cmd_list([])
    captured = capsys.readouterr()
    assert "orphaned" in captured.out
    assert nonexistent_path in captured.out
