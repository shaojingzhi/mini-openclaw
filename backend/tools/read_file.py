"""Project-root-restricted ``read_file`` tool for the Mini-OpenClaw agent.

Wraps ``langchain_community.tools.file_management.ReadFileTool`` with
``root_dir`` pinned to the project root. The underlying tool already rejects
paths that resolve outside ``root_dir`` (absolute paths like ``/etc/passwd``
or ``..`` traversal), returning a fixed ``Access denied`` error string, so
all we add here is the project-root binding and the ``@tool`` wrapper that
gives it a typed ``args_schema`` and the agent-facing docstring.
"""

from __future__ import annotations

from pathlib import Path

from langchain_community.tools.file_management import ReadFileTool
from langchain_core.tools import tool

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

_READ_FILE_TOOL: ReadFileTool = ReadFileTool(root_dir=str(PROJECT_ROOT))


@tool("read_file")
def read_file(file_path: str) -> str:
    """Read a project file relative to the project root.

    Use to inspect source files, ``SKILL.md`` content, configuration files,
    or anything else inside the project tree. Paths that escape the project
    root (e.g. ``/etc/passwd`` or ``../../something``) are rejected with an
    error string and the file is not read.

    Args:
        file_path: Path relative to the project root. Absolute paths or
            ``..`` segments that resolve outside the project root are
            refused.

    Returns:
        The file content as text, or an error string if the path is
        outside the project root or the file does not exist.
    """
    return _READ_FILE_TOOL.invoke({"file_path": file_path})


__all__ = ["read_file", "PROJECT_ROOT"]
