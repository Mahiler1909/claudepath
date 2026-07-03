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


def test_encode_replaces_dots():
    # Dots are replaced with hyphens (verified against real ~/.claude/projects/ data:
    # /Users/.../local.tmp/... -> -Users-...-local-tmp-...)
    assert encode_path("/Users/foo/local.tmp/proj") == "-Users-foo-local-tmp-proj"


def test_encode_replaces_leading_dot_dirs():
    # /.config -> /-config (two hyphens: one for '/', one for '.')
    assert encode_path("/Users/foo/.config/project") == "-Users-foo--config-project"


def test_encode_replaces_tilde():
    # ~ is replaced with - (per anthropics/claude-code#19972)
    assert encode_path("/tmp/host.example/~user/proj") == "-tmp-host-example--user-proj"


def test_encode_replaces_underscore():
    # _ is replaced with - (confirmed in real ~/.claude/projects/ data)
    assert encode_path("/Users/foo/my_project") == "-Users-foo-my-project"


def test_encode_replaces_spaces_and_punctuation():
    assert encode_path("/Users/foo/My Project (v2)") == "-Users-foo-My-Project--v2-"


def test_encode_replaces_backslash_and_colon():
    # Windows-style separators and the drive-letter colon are all replaced
    assert encode_path("C:\\Users\\foo\\bar") == "C--Users-foo-bar"


def test_encode_replaces_non_ascii_bmp():
    # BMP non-ASCII characters: one '-' per code point
    assert encode_path("/Users/foo/研究/proj") == "-Users-foo----proj"


def test_encode_replaces_non_bmp_emoji():
    # Non-BMP code points (e.g. emoji) occupy two UTF-16 code units, so they
    # collapse to TWO hyphens — matching JS's charCodeAt iteration.
    assert encode_path("/Users/foo/🦀/proj") == "-Users-foo----proj"


def test_encode_truncates_long_paths_with_hash():
    # Encoded names > 200 chars are truncated and suffixed with a base-36
    # 32-bit hash of the original path. Validated against the JS reference.
    long_path = "/x/" + "a" * 300
    encoded = encode_path(long_path)
    expected_prefix = "-x-" + "a" * 197  # 200 chars total
    assert encoded == expected_prefix + "-rtseee"
    assert len(encoded.rsplit("-", 1)[0]) == 200


def test_encode_matches_real_data():
    # Verified against actual ~/.claude/projects/ directory names
    assert (
        encode_path("/Users/Mahiler1909/Documents/personal/claude-code-project-mover")
        == "-Users-Mahiler1909-Documents-personal-claude-code-project-mover"
    )
    assert (
        encode_path("/Users/gmasse/Documents/Dev/local.tmp/higuest/backend")
        == "-Users-gmasse-Documents-Dev-local-tmp-higuest-backend"
    )
