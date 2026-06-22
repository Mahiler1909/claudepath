from claudepath.encoder import encode_path


def test_encode_simple_path():
    assert encode_path("/Users/foo/bar") == "-Users-foo-bar"


def test_encode_preserves_hyphens_in_dir_names():
    # Hyphens in directory names stay as-is
    assert encode_path("/Users/foo/my-project") == "-Users-foo-my-project"


def test_encode_deep_path():
    result = encode_path("/Users/Mahiler1909/Documents/personal/ai-workspace")
    assert result == "-Users-Mahiler1909-Documents-personal-ai-workspace"


def test_encode_root():
    assert encode_path("/") == "-"


def test_encode_spaces_in_dir_names():
    # Spaces are encoded as hyphens — empirically verified
    assert encode_path("/Users/foo/my project") == "-Users-foo-my-project"
    assert encode_path("/Users/foo/Competitive Agent Demo") == "-Users-foo-Competitive-Agent-Demo"


def test_encode_dots_in_dir_names():
    # Dots are encoded as hyphens — empirically verified against real Claude Code data
    assert encode_path("/private/tmp/test.directory") == "-private-tmp-test-directory"
    assert encode_path("/Users/foo/.config/project") == "-Users-foo--config-project"


def test_encode_tildes_in_dir_names():
    # Tildes are encoded as hyphens — empirically verified against real Claude Code data
    assert encode_path("/private/tmp/test~directory") == "-private-tmp-test-directory"


def test_encode_all_special_chars():
    # All non-alphanumeric, non-hyphen characters encode as '-' — empirically
    # verified against real Claude Code data for: @ . ~ space _ ( ) ' ' # & + ! % $ [ ] = , ; ^
    assert encode_path("/Users/foo/GoogleDrive-user@host.com/proj") == "-Users-foo-GoogleDrive-user-host-com-proj"
    assert encode_path("/Users/foo/my_project") == "-Users-foo-my-project"
    assert encode_path("/Users/foo/Project (2024)") == "-Users-foo-Project--2024-"
    assert encode_path("/Users/foo/Brent's Notes") == "-Users-foo-Brent-s-Notes"


def test_encode_matches_real_data():
    # Verified against actual ~/.claude/projects/ directory names
    assert (
        encode_path("/Users/Mahiler1909/Documents/personal/claude-code-project-mover")
        == "-Users-Mahiler1909-Documents-personal-claude-code-project-mover"
    )
    # Space in name — verified on macOS Claude Code desktop
    assert (
        encode_path("/Users/bsleeper/Desktop/Competitive Agent Demo")
        == "-Users-bsleeper-Desktop-Competitive-Agent-Demo"
    )
    # Dot and tilde — verified on macOS Claude Code desktop
    assert (
        encode_path("/private/tmp/claudepath-test-dot.directory")
        == "-private-tmp-claudepath-test-dot-directory"
    )
    assert (
        encode_path("/private/tmp/claudepath-test-tilde~directory")
        == "-private-tmp-claudepath-test-tilde-directory"
    )
