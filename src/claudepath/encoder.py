"""
Path encoding utilities for Claude Code project directories.

Claude Code encodes project paths by replacing every '/' with '-'.
Example: /Users/foo/my-project -> -Users-foo-my-project

This is validated against real ~/.claude/projects/ directory names.
Note: decoding is ambiguous (hyphens in dir names vs path separators),
so we never decode - we always work from known absolute paths.
"""


def encode_path(abs_path: str) -> str:
    """Convert an absolute path to the Claude Code encoded directory name.

    /Users/foo/bar -> -Users-foo-bar
    """
    return abs_path.replace("/", "-")
