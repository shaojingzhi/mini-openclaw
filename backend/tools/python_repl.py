"""Python REPL tool for the Mini-OpenClaw agent.

Wraps ``langchain_experimental.tools.PythonREPLTool`` so the agent can perform
arithmetic, light scripting, or quick data manipulation. Output is stripped of
trailing whitespace so that, for example, ``print(2+2)`` returns ``"4"`` rather
than ``"4\n"``.
"""

from __future__ import annotations

from langchain_core.tools import tool
from langchain_experimental.tools import PythonREPLTool

_REPL_TOOL: PythonREPLTool = PythonREPLTool()


@tool("python_repl")
def python_repl(query: str) -> str:
    """Execute a Python snippet and return its stdout.

    Use ``print(...)`` to surface values; the return value of the snippet
    itself is not captured. Imports such as ``math`` work as in a normal
    Python session.

    Args:
        query: A Python code string to execute.

    Returns:
        The captured stdout of the snippet with trailing whitespace stripped.
    """
    raw = _REPL_TOOL.invoke(query)
    return raw.rstrip()


__all__ = ["python_repl"]
