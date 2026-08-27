"""User-scoped filesystem helpers for Mini-OpenClaw."""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT: Path = Path(__file__).resolve().parents[1]
DATA_USERS_DIR: Path = PROJECT_ROOT / "backend" / "data" / "users"
DEFAULT_USER_ID = "anonymous"
_VALID_USER_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def normalize_user_id(user_id: str | None) -> str:
    if user_id is None:
        return DEFAULT_USER_ID
    value = user_id.strip()
    if not value:
        return DEFAULT_USER_ID
    if value in {".", ".."} or not _VALID_USER_ID_RE.match(value):
        raise ValueError(f"invalid user id: {user_id!r}")
    return value


def user_root(user_id: str | None) -> Path:
    return DATA_USERS_DIR / normalize_user_id(user_id)


def user_sessions_dir(user_id: str | None) -> Path:
    return user_root(user_id) / "sessions"


def user_memory_dir(user_id: str | None) -> Path:
    return user_root(user_id) / "memory"


def user_workspace_dir(user_id: str | None) -> Path:
    return user_root(user_id) / "workspace"


__all__ = [
    "DATA_USERS_DIR",
    "DEFAULT_USER_ID",
    "normalize_user_id",
    "user_memory_dir",
    "user_root",
    "user_sessions_dir",
    "user_workspace_dir",
]
