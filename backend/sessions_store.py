"""Session persistence for Mini-OpenClaw.

Sessions are JSON arrays stored at ``backend/sessions/{session_name}.json``.
Each element is a message dict with at least a ``role`` (``user`` /
``assistant`` / ``tool``) and a ``content`` field; assistant tool calls and
tool results may carry additional fields (``tool_calls``, ``name``,
``tool_call_id``), which we round-trip verbatim.

Design notes:
- Loading a non-existent session returns an empty list (never raises).
- ``append_message`` lazily creates ``backend/sessions/`` and the JSON file
  on the first append, so callers never need an explicit init step.
- The session name is constrained to a small charset (letters, digits,
  ``-`` / ``_`` / ``.``) so a caller can never traverse out of
  ``SESSIONS_DIR`` via a crafted name.
- ``SESSIONS_DIR`` is a module-level constant (not a default arg) so tests
  can monkey-patch it with ``patch.object(ss_mod, "SESSIONS_DIR", tmp)``
  — same pattern documented for ``KNOWLEDGE_DIR`` (US-008) and
  ``WORKSPACE_DIR`` (US-011).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from backend.user_state import DEFAULT_USER_ID, normalize_user_id, user_sessions_dir

PROJECT_ROOT: Path = Path(__file__).resolve().parents[1]
SESSIONS_DIR: Path = PROJECT_ROOT / "backend" / "sessions"

ALLOWED_ROLES: tuple[str, ...] = ("user", "assistant", "tool")

# Letters, digits, dash, underscore, dot. No slashes, no `..`.
_VALID_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _validate_session_name(name: str) -> None:
    """Raise ``ValueError`` for names that could escape ``SESSIONS_DIR``."""
    if not isinstance(name, str) or not name:
        raise ValueError("session name must be a non-empty string")
    if name in (".", ".."):
        raise ValueError(f"invalid session name: {name!r}")
    if not _VALID_NAME_RE.match(name):
        raise ValueError(
            f"invalid session name: {name!r}; allowed chars are A-Z a-z 0-9 . _ -"
        )


def _session_path(name: str, user_id: str | None = None) -> Path:
    """Return the on-disk JSON path for ``name``.

    Anonymous/default traffic keeps using the legacy shared sessions directory so
    existing single-user flows continue to work unchanged, while named users are
    isolated under ``backend/data/users/{user_id}/sessions``. Reads
    ``SESSIONS_DIR`` from module globals each call so ``patch.object`` in tests
    takes effect.
    """
    _validate_session_name(name)
    if user_id is None or normalize_user_id(user_id) == DEFAULT_USER_ID:
        return SESSIONS_DIR / f"{name}.json"
    return user_sessions_dir(user_id) / f"{name}.json"


def load_session(name: str, user_id: str | None = None) -> list[dict[str, Any]]:
    """Return the message list for ``name``.

    Non-existent sessions return ``[]`` (no exception). Corrupt JSON also
    returns ``[]`` so a single bad file cannot crash agent startup — callers
    that need to distinguish "empty" from "corrupt" should re-read the file
    directly.
    """
    path = _session_path(name, user_id=user_id)
    if not path.exists():
        return []
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return []
    if not raw.strip():
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def append_message(name: str, message: dict[str, Any], user_id: str | None = None) -> list[dict[str, Any]]:
    """Append ``message`` to session ``name`` and return the new full list.

    Validates that ``message`` is a dict with a ``role`` in
    :data:`ALLOWED_ROLES`. Creates ``SESSIONS_DIR`` and the JSON file on
    first append. The on-disk file is rewritten atomically (write to a
    sibling ``.tmp`` then ``replace``) so a crash mid-write cannot corrupt
    an existing session.
    """
    if not isinstance(message, dict):
        raise TypeError(f"message must be a dict, got {type(message).__name__}")
    role = message.get("role")
    if role not in ALLOWED_ROLES:
        raise ValueError(
            f"message role must be one of {ALLOWED_ROLES}, got {role!r}"
        )

    path = _session_path(name, user_id=user_id)
    path.parent.mkdir(parents=True, exist_ok=True)

    messages = load_session(name, user_id=user_id)
    messages.append(message)

    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(messages, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)

    return messages


__all__ = [
    "ALLOWED_ROLES",
    "PROJECT_ROOT",
    "SESSIONS_DIR",
    "append_message",
    "load_session",
]
