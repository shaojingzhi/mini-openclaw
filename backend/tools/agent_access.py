"""Shared path policy for agent-scoped filesystem tools."""

from __future__ import annotations

from pathlib import Path

from backend.agents.profiles import normalize_agent_id

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PRIVATE_MEMORY_MARKER = ("approved_memory", "agents")


def can_access_project_path(
    raw_path: str,
    *,
    agent_id: str,
    project_root: Path = PROJECT_ROOT,
) -> bool:
    """Return whether a project path is outside other agents' private projections."""
    root = project_root.resolve()
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        parts = candidate.resolve().relative_to(root).parts
    except (OSError, ValueError):
        return False

    normalized_agent_id = normalize_agent_id(agent_id)
    for index in range(len(parts) - 1):
        if parts[index : index + 2] != PRIVATE_MEMORY_MARKER:
            continue
        owner_index = index + 2
        return owner_index < len(parts) and parts[owner_index] == normalized_agent_id
    return True


__all__ = ["PRIVATE_MEMORY_MARKER", "PROJECT_ROOT", "can_access_project_path"]
