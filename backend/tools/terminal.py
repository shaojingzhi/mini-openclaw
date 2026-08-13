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
import subprocess
from pathlib import Path

from langchain_community.tools import ShellTool
from langchain_core.tools import BaseTool, tool

from backend.agents.profiles import normalize_agent_id
from backend.tools.agent_access import can_access_project_path

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
SCOPED_BLOCKED_MESSAGE = (
    "[terminal] refused: command is outside the agent-safe allowlist or crosses "
    "a private-memory boundary."
)
TERMINAL_TIMEOUT_SECONDS = 30
_ALLOWED_GIT_SUBCOMMANDS = {"diff", "log", "show", "status"}
_ALLOWED_LS_OPTIONS = {"-1", "-a", "-al", "-l", "-la"}
_ALLOWED_NPM_SCRIPTS = {"build", "lint", "test", "typecheck"}
_SHELL_SYNTAX = ("&&", "||", "$(", "`", "|", ";", ">", "<")

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


def _private_memory_path_allowed(argument: str, *, agent_id: str) -> bool:
    marker = "approved_memory/agents"
    if marker not in argument:
        return True
    path_start = argument.find(marker)
    return can_access_project_path(argument[path_start:], agent_id=agent_id)


def _is_agent_safe_command(arguments: list[str], *, agent_id: str) -> bool:
    if not arguments:
        return False
    if any(not _private_memory_path_allowed(argument, agent_id=agent_id) for argument in arguments):
        return False

    executable = Path(arguments[0]).name
    if executable == "pwd":
        return len(arguments) == 1
    if executable == "ls":
        paths = [argument for argument in arguments[1:] if not argument.startswith("-")]
        options = [argument for argument in arguments[1:] if argument.startswith("-")]
        return all(option in _ALLOWED_LS_OPTIONS for option in options) and all(
            can_access_project_path(path, agent_id=agent_id) for path in paths
        )
    if executable == "git":
        if len(arguments) < 2 or arguments[1] not in _ALLOWED_GIT_SUBCOMMANDS:
            return False
        if "--no-index" in arguments:
            return False
        return all(
            not argument.startswith("/")
            or can_access_project_path(argument, agent_id=agent_id)
            for argument in arguments[2:]
        )
    if executable == "npm":
        root_script = (
            len(arguments) == 3
            and arguments[1] == "run"
            and arguments[2] in _ALLOWED_NPM_SCRIPTS
        )
        frontend_script = (
            len(arguments) == 5
            and arguments[1:4] == ["--prefix", "frontend", "run"]
            and arguments[4] in _ALLOWED_NPM_SCRIPTS
        )
        return root_script or frontend_script
    if executable in {"python", "python3"}:
        return len(arguments) >= 3 and arguments[1:3] == ["-m", "unittest"]
    return False


def _run_agent_safe_command(arguments: list[str]) -> str:
    try:
        result = subprocess.run(
            arguments,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=TERMINAL_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"[terminal] command failed: {exc}"
    output = "\n".join(part for part in (result.stdout.rstrip(), result.stderr.rstrip()) if part)
    return output or f"process exited with code {result.returncode}"


def build_terminal_tool(*, agent_id: str) -> BaseTool:
    """Build a no-shell terminal constrained to auditable development commands."""
    normalized_agent_id = normalize_agent_id(agent_id)

    @tool("terminal")
    def scoped_terminal(command: str) -> str:
        """Run one allowlisted development command without shell expansion.

        Supported commands are ``pwd``, non-recursive ``ls``, selected read-only
        ``git`` commands, configured ``npm run`` checks, and ``python -m unittest``.
        Pipes, redirects, arbitrary interpreters, and other agents' private memory
        paths are not executable through this tool.
        """
        if any(syntax in command for syntax in _SHELL_SYNTAX):
            return SCOPED_BLOCKED_MESSAGE
        try:
            arguments = shlex.split(command)
        except ValueError:
            return SCOPED_BLOCKED_MESSAGE
        if not _is_agent_safe_command(arguments, agent_id=normalized_agent_id):
            return SCOPED_BLOCKED_MESSAGE
        return _run_agent_safe_command(arguments)

    return scoped_terminal


__all__ = [
    "BLOCKED_MESSAGE",
    "PROJECT_ROOT",
    "SCOPED_BLOCKED_MESSAGE",
    "build_terminal_tool",
    "terminal",
]
