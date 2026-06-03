"""Sandboxed terminal tool for the Mini-OpenClaw agent.

Wraps ``langchain_community.tools.ShellTool`` so that every command runs from
the project root and a small blacklist of obviously destructive commands is
rejected before reaching the shell.

The underlying ``BashProcess`` has no ``cwd`` parameter, so we pin the working
directory by prefixing each command with ``cd <project-root> && ...``. The
blacklist is matched against the raw command string before any execution.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

from langchain_community.tools import ShellTool
from langchain_core.tools import tool

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

_BLACKLIST: tuple[re.Pattern[str], ...] = (
    re.compile(r"\brm\s+-rf\s+/"),
    re.compile(r"\brm\s+-rf\s+~"),
    re.compile(r":\s*\(\s*\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:"),
    re.compile(r"\bmkfs\b"),
    re.compile(r"\bdd\s+if="),
)

BLOCKED_MESSAGE: str = (
    "[terminal] refused: command matches the destructive-command blacklist "
    "and was not executed."
)

_SHELL_TOOL: ShellTool = ShellTool()


def _is_blacklisted(command: str) -> bool:
    return any(pattern.search(command) for pattern in _BLACKLIST)


def _run_in_root(command: str) -> str:
    prefixed = f"cd {shlex.quote(str(PROJECT_ROOT))} && ({command})"
    return _SHELL_TOOL.process.run(prefixed)


@tool("terminal")
def terminal(command: str) -> str:
    """Run a shell command from the project root.

    Use for filesystem inspection, build/test commands, or quick OS-level
    operations. Destructive commands (e.g. ``rm -rf /``, ``mkfs``, ``dd if=``)
    are blocked and return a refusal string without executing.

    Args:
        command: The shell command string to execute.

    Returns:
        Combined stdout/stderr of the command, or a refusal string if the
        command matches the destructive blacklist.
    """
    if _is_blacklisted(command):
        return BLOCKED_MESSAGE
    return _run_in_root(command)


__all__ = ["terminal", "BLOCKED_MESSAGE", "PROJECT_ROOT"]
