"""Subprocess-backed Python REPL tool for the Mini-OpenClaw agent."""

from __future__ import annotations

import ast
import os
import signal
import subprocess
import sys
import tempfile
from typing import Final

from backend.settings import get_settings
from langchain_core.tools import tool

PYTHON_REPL_TIMEOUT_SECONDS: Final[float] = (
    get_settings().python_repl_timeout_seconds
)
PYTHON_REPL_MEMORY_LIMIT_BYTES: Final[int] = (
    get_settings().python_repl_memory_limit_bytes
)
CPU_TIMEOUT_SIGNAL: Final[int | None] = getattr(signal, "SIGXCPU", None)

SAFE_IMPORT_ROOTS: Final[set[str]] = {
    "collections",
    "datetime",
    "decimal",
    "fractions",
    "functools",
    "itertools",
    "json",
    "math",
    "random",
    "re",
    "statistics",
}
BLOCKED_CALLS: Final[set[str]] = {
    "__import__",
    "compile",
    "eval",
    "exec",
    "input",
    "open",
}
BLOCKED_ATTRS: Final[set[str]] = {
    "chmod",
    "chown",
    "fork",
    "mkdir",
    "open",
    "popen",
    "remove",
    "rename",
    "replace",
    "rmdir",
    "rmtree",
    "spawn",
    "system",
    "unlink",
    "write_bytes",
    "write_text",
}


class UnsafePythonError(ValueError):
    """Raised when a snippet asks for capabilities outside the REPL sandbox."""


def _validate_safe_python(code: str) -> None:
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        raise UnsafePythonError(f"syntax error: {exc.msg}") from exc

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            _validate_import(node)
        elif isinstance(node, ast.Call):
            _validate_call(node)


def _validate_import(node: ast.Import | ast.ImportFrom) -> None:
    modules: list[str] = []
    if isinstance(node, ast.Import):
        modules = [alias.name for alias in node.names]
    elif node.module:
        modules = [node.module]

    for module in modules:
        root = module.split(".", 1)[0]
        if root not in SAFE_IMPORT_ROOTS:
            raise UnsafePythonError(f"import '{root}' is not allowed")


def _validate_call(node: ast.Call) -> None:
    if isinstance(node.func, ast.Name) and node.func.id in BLOCKED_CALLS:
        raise UnsafePythonError(f"call '{node.func.id}' is not allowed")
    if isinstance(node.func, ast.Attribute) and node.func.attr in BLOCKED_ATTRS:
        raise UnsafePythonError(f"attribute '{node.func.attr}' is not allowed")


def _sandbox_env() -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUNBUFFERED": "1",
    }


def _timeout_error() -> str:
    return (
        "Error: python_repl timed out after "
        f"{PYTHON_REPL_TIMEOUT_SECONDS:.0f} seconds."
    )


def _apply_resource_limits() -> None:
    try:
        import resource
    except ImportError:
        return

    limits = [
        (resource.RLIMIT_CPU, (2, 2)),
        (
            resource.RLIMIT_AS,
            (PYTHON_REPL_MEMORY_LIMIT_BYTES, PYTHON_REPL_MEMORY_LIMIT_BYTES),
        ),
    ]
    for limit_name, values in limits:
        try:
            resource.setrlimit(limit_name, values)
        except (OSError, ValueError):
            # macOS and some containers reject specific resource limits.
            continue


def _run_subprocess(code: str) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory(prefix="mini-openclaw-python-repl-") as tmp:
        return subprocess.run(
            [sys.executable, "-I", "-S", "-c", code],
            cwd=tmp,
            env=_sandbox_env(),
            capture_output=True,
            text=True,
            timeout=PYTHON_REPL_TIMEOUT_SECONDS,
            preexec_fn=_apply_resource_limits if os.name == "posix" else None,
            check=False,
        )


@tool("python_repl")
def python_repl(query: str) -> str:
    """Execute a Python snippet in an isolated subprocess and return stdout.

    Use ``print(...)`` to surface values; the return value of the snippet
    itself is not captured. Safe standard-library imports such as ``math``
    are allowed, while filesystem/process operations are blocked.

    Args:
        query: A Python code string to execute.

    Returns:
        The captured stdout of the snippet with trailing whitespace stripped.
    """
    try:
        _validate_safe_python(query)
        result = _run_subprocess(query)
    except UnsafePythonError as exc:
        return f"Error: python_repl blocked unsafe code ({exc})."
    except subprocess.TimeoutExpired:
        return _timeout_error()

    stdout = result.stdout.rstrip()
    stderr = result.stderr.rstrip()
    if result.returncode != 0:
        if CPU_TIMEOUT_SIGNAL is not None and result.returncode == -CPU_TIMEOUT_SIGNAL:
            return _timeout_error()
        detail = stderr or stdout or f"process exited with code {result.returncode}"
        return f"Error: python_repl failed: {detail}"
    return stdout


__all__ = [
    "PYTHON_REPL_TIMEOUT_SECONDS",
    "UnsafePythonError",
    "python_repl",
]
