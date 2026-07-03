"""
Path encoding utilities for Claude Code project directories.

Claude Code replaces every non-ASCII-alphanumeric character in an absolute
path with '-' (path separators, dots, tildes, underscores, spaces, non-ASCII,
even existing hyphens — hyphens just map to themselves). If the encoded name
exceeds 200 characters, it's truncated to 200 and a base-36 32-bit hash of
the original path is appended after a hyphen.

Reference: extracted from Claude Code 2.1.177 binary; matches the source
in https://github.com/anthropics/claude-code/issues/19972.

Note: the encoding is lossy and non-reversible, so we never decode —
we always work from known absolute paths.
"""

_MAX_ENCODED_LEN = 200


def encode_path(abs_path: str) -> str:
    """Convert an absolute path to the Claude Code encoded directory name.

    /Users/foo/bar         -> -Users-foo-bar
    /Users/foo/local.tmp   -> -Users-foo-local-tmp
    /tmp/host.example/~u   -> -tmp-host-example--u
    /Users/foo/my_project  -> -Users-foo-my-project

    Paths whose encoded form exceeds 200 chars are truncated with a hash suffix:
    /very/long/path/...    -> -very-long-path-...-<base36 hash>
    """
    replaced = _replace_non_alnum(abs_path)
    if len(replaced) <= _MAX_ENCODED_LEN:
        return replaced
    return f"{replaced[:_MAX_ENCODED_LEN]}-{_path_hash(abs_path)}"


def _replace_non_alnum(s: str) -> str:
    """Replace every UTF-16 code unit that isn't ASCII alphanumeric with '-'.

    Iterates UTF-16 code units (not Python code points) so non-BMP characters
    like emoji collapse to two hyphens — matching JS's per-code-unit iteration
    in the reference implementation (`/[^a-zA-Z0-9]/g` over a JS string).
    """
    raw = s.encode("utf-16-le")
    out = []
    for i in range(0, len(raw), 2):
        cu = raw[i] | (raw[i + 1] << 8)
        if (0x30 <= cu <= 0x39) or (0x41 <= cu <= 0x5A) or (0x61 <= cu <= 0x7A):
            out.append(chr(cu))
        else:
            out.append("-")
    return "".join(out)


def _path_hash(s: str) -> str:
    """djb2-like 32-bit signed hash matching JS: ((h<<5) - h + s.charCodeAt(i)) | 0.

    JS's charCodeAt returns UTF-16 code units, so we encode to UTF-16-LE and
    iterate 16-bit values (matters only for non-BMP characters).
    """
    h = 0
    raw = s.encode("utf-16-le")
    for i in range(0, len(raw), 2):
        code_unit = raw[i] | (raw[i + 1] << 8)
        h = ((h << 5) - h + code_unit) & 0xFFFFFFFF
        if h >= 0x80000000:
            h -= 0x100000000
    return _to_base36(abs(h))


def _to_base36(n: int) -> str:
    if n == 0:
        return "0"
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    out = []
    while n:
        n, r = divmod(n, 36)
        out.append(digits[r])
    return "".join(reversed(out))
