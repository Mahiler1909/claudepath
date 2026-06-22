"""
Path encoding utilities for Claude Code project directories.

Claude Code encodes project paths by replacing every non-alphanumeric,
non-hyphen character with '-'. Empirically verified against real
~/.claude/projects/ directory names on macOS (Claude Code desktop):

  Characters confirmed encoded as '-':
    / (path separator), space, . ~ @ _ ( ) ' ' # & + ! % $ [ ] = , ; ^

  Characters confirmed preserved:
    a-z, A-Z, 0-9, - (hyphen)

Claude Code also resolves symlinks before encoding (e.g. /tmp ->
/private/tmp on macOS), so abs_path should already be fully resolved.

Note: decoding is ambiguous — any of the above special characters and
'-' itself all map to '-', so we never decode. We always work from
known absolute paths.
"""

import re

_ENCODE_RE = re.compile(r"[^a-zA-Z0-9-]")


def encode_path(abs_path: str) -> str:
    """Convert an absolute path to the Claude Code encoded directory name."""
    return _ENCODE_RE.sub("-", abs_path)
