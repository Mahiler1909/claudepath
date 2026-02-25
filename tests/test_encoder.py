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


def test_encode_does_not_modify_dots():
    # Dots should NOT be replaced (validated against real ~/.claude/projects/ data)
    assert encode_path("/Users/foo/.config/project") == "-Users-foo-.config-project"


def test_encode_matches_real_data():
    # Verified against actual ~/.claude/projects/ directory names
    assert (
        encode_path("/Users/Mahiler1909/Documents/personal/claude-code-project-mover")
        == "-Users-Mahiler1909-Documents-personal-claude-code-project-mover"
    )
