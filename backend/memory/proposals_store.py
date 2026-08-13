"""Auditable, user-scoped candidate memory proposal storage.

The module intentionally exposes plain Python functions instead of FastAPI or
LangChain objects so the same service can later sit behind an MCP server.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from backend import user_state
from backend.agents.profiles import DEFAULT_AGENT_ID, list_agent_profiles, normalize_agent_id
from backend.user_state import DEFAULT_USER_ID, normalize_user_id, user_memory_dir

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MEMORY_DIR = PROJECT_ROOT / "backend" / "memory"
PROPOSALS_FILENAME = "memory_proposals.jsonl"
MAX_BOOTSTRAP_MEMORIES = 12

MemoryTarget = Literal[
    "user_capsule",
    "project_memory",
    "agent_behavior",
    "relationship_memory",
]
MemoryType = Literal[
    "user_preference",
    "project_convention",
    "task_state",
    "behavior_preference",
]
MemoryConfidence = Literal["low", "medium", "high"]
MemorySignalKind = Literal[
    "user_instructed",
    "explicit_preference",
    "repeated_feedback",
    "project_decision",
]
MemoryScope = Literal["global", "project", "task", "interview_prep"]
ProposalStatus = Literal["pending", "approved", "rejected"]
MemoryVisibility = Literal["shared", "agent_private"]

_VALID_TARGETS = {
    "user_capsule",
    "project_memory",
    "agent_behavior",
    "relationship_memory",
}
_VALID_TYPES = {
    "user_preference",
    "project_convention",
    "task_state",
    "behavior_preference",
}
_VALID_CONFIDENCES = {"low", "medium", "high"}
_VALID_SIGNAL_KINDS = {
    "user_instructed",
    "explicit_preference",
    "repeated_feedback",
    "project_decision",
}
_VALID_SCOPES = {"global", "project", "task", "interview_prep"}
_VALID_STATUSES = {"pending", "approved", "rejected"}
_STORE_LOCK = threading.RLock()

_LAYER_METADATA: dict[str, tuple[str, str]] = {
    "agent_behavior": ("AGENT.md", "Agent Persona"),
    "user_capsule": ("USER.md", "User Profile"),
    "project_memory": ("PROJECT.md", "Project Memory"),
    "relationship_memory": ("RELATIONSHIP.md", "Relationship Primer"),
}
MATERIALIZED_DIRNAME = "approved_memory"
_PRIVATE_TARGETS = {"agent_behavior", "relationship_memory"}


class ProposalNotFoundError(LookupError):
    """Raised when a proposal does not exist in the current user's store."""


class ProposalStateError(ValueError):
    """Raised when a proposal decision is invalid for its current state."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _memory_dir_for_user(user_id: str) -> Path:
    return MEMORY_DIR if user_id == DEFAULT_USER_ID else user_memory_dir(user_id)


def proposals_path(user_id: str | None = None) -> Path:
    """Return the service-owned proposal file for one user namespace."""
    normalized_user_id = normalize_user_id(user_id)
    return _memory_dir_for_user(normalized_user_id) / PROPOSALS_FILENAME


def materialized_memory_dir(user_id: str | None = None) -> Path:
    """Return the server-owned Markdown projection directory for one user."""
    normalized_user_id = normalize_user_id(user_id)
    return _memory_dir_for_user(normalized_user_id) / MATERIALIZED_DIRNAME


def materialized_memory_paths(
    user_id: str | None = None,
    agent_id: str = DEFAULT_AGENT_ID,
) -> dict[str, Path]:
    """Return the fixed target-to-Markdown mapping for a user's projection."""
    return _materialized_memory_paths_for_dir(
        materialized_memory_dir(user_id),
        agent_id=agent_id,
    )


def _materialized_memory_paths_for_dir(
    directory: Path,
    *,
    agent_id: str = DEFAULT_AGENT_ID,
) -> dict[str, Path]:
    normalized_agent_id = normalize_agent_id(agent_id)
    paths: dict[str, Path] = {}
    for target, (filename, _) in _LAYER_METADATA.items():
        if target in _PRIVATE_TARGETS:
            paths[target] = directory / "agents" / normalized_agent_id / filename
        else:
            paths[target] = directory / filename
    return paths


def _read_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    records: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict) and isinstance(record.get("proposal_id"), str):
            records.append(record)
    return records


def _write_records(path: Path, records: list[dict[str, Any]]) -> None:
    staged_path = _stage_records(path, records)
    try:
        _commit_staged_records(staged_path, path)
    except Exception:
        staged_path.unlink(missing_ok=True)
        raise


def _stage_records(path: Path, records: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records)
    staged_path = path.with_name(f".{path.name}.stage-{uuid.uuid4().hex}")
    staged_path.write_text(body, encoding="utf-8")
    return staged_path


def _commit_staged_records(staged_path: Path, target_path: Path) -> None:
    staged_path.replace(target_path)


def _required_text(value: str, *, name: str, limit: int) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} must not be empty")
    if len(normalized) > limit:
        raise ValueError(f"{name} must be at most {limit} characters")
    return normalized


def _optional_text(value: str | None, *, name: str, limit: int) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > limit:
        raise ValueError(f"{name} must be at most {limit} characters")
    return normalized


def _validate_choice(value: str, *, name: str, allowed: set[str]) -> str:
    if value not in allowed:
        choices = ", ".join(sorted(allowed))
        raise ValueError(f"{name} must be one of: {choices}")
    return value


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _copy_record(record: dict[str, Any]) -> dict[str, Any]:
    copied = dict(record)
    target = str(copied.get("target", ""))
    owner, visibility = _memory_owner(target, copied.get("agent_id"))
    copied["agent_id"] = owner
    copied["visibility"] = visibility
    return copied


def _memory_owner(target: str, agent_id: str | None) -> tuple[str | None, MemoryVisibility]:
    if target in _PRIVATE_TARGETS:
        return normalize_agent_id(agent_id), "agent_private"
    return None, "shared"


def _record_owner(record: dict[str, Any]) -> str | None:
    target = str(record.get("target", ""))
    if target not in _PRIVATE_TARGETS:
        return None
    return normalize_agent_id(record.get("agent_id") or DEFAULT_AGENT_ID)


def is_memory_visible_to_agent(record: dict[str, Any], agent_id: str) -> bool:
    normalized_agent_id = normalize_agent_id(agent_id)
    target = str(record.get("target", ""))
    return target not in _PRIVATE_TARGETS or _record_owner(record) == normalized_agent_id


def create_proposal(
    *,
    user_id: str | None,
    session_id: str | None,
    agent_id: str | None = None,
    target: MemoryTarget,
    memory_type: MemoryType,
    content: str,
    rationale: str,
    confidence: MemoryConfidence = "medium",
    signal_kind: MemorySignalKind = "explicit_preference",
    scope: MemoryScope = "global",
    source_message_id: str | None = None,
    client_request_id: str | None = None,
) -> tuple[dict[str, Any], bool]:
    """Create a pending proposal, returning ``(proposal, created)``.

    ``client_request_id`` is an MCP-friendly idempotency key. Exact matching
    pending or approved content is also reused so retries cannot spam review.
    """
    normalized_user_id = normalize_user_id(user_id)
    normalized_target = _validate_choice(target, name="target", allowed=_VALID_TARGETS)
    normalized_type = _validate_choice(memory_type, name="memory_type", allowed=_VALID_TYPES)
    normalized_confidence = _validate_choice(confidence, name="confidence", allowed=_VALID_CONFIDENCES)
    normalized_signal = _validate_choice(signal_kind, name="signal_kind", allowed=_VALID_SIGNAL_KINDS)
    normalized_scope = _validate_choice(scope, name="scope", allowed=_VALID_SCOPES)
    normalized_agent_id, visibility = _memory_owner(normalized_target, agent_id)
    normalized_content = _required_text(content, name="content", limit=2_000)
    normalized_rationale = _required_text(rationale, name="rationale", limit=1_000)
    normalized_source_message_id = _optional_text(source_message_id, name="source_message_id", limit=200)
    normalized_request_id = _optional_text(client_request_id, name="client_request_id", limit=200)
    content_hash = _content_hash(normalized_content)
    path = proposals_path(normalized_user_id)

    with _STORE_LOCK:
        records = _read_records(path)
        for record in records:
            if normalized_request_id and record.get("client_request_id") == normalized_request_id:
                return _copy_record(record), False
            if (
                record.get("target") == normalized_target
                and record.get("memory_type") == normalized_type
                and record.get("content_hash") == content_hash
                and _record_owner(record) == normalized_agent_id
                and record.get("status") in {"pending", "approved"}
            ):
                return _copy_record(record), False

        proposal = {
            "proposal_id": f"memprop_{uuid.uuid4().hex}",
            "status": "pending",
            "user_id": normalized_user_id,
            "session_id": _optional_text(session_id, name="session_id", limit=200),
            "agent_id": normalized_agent_id,
            "visibility": visibility,
            "target": normalized_target,
            "memory_type": normalized_type,
            "content": normalized_content,
            "content_hash": content_hash,
            "rationale": normalized_rationale,
            "confidence": normalized_confidence,
            "signal_kind": normalized_signal,
            "scope": normalized_scope,
            "source_message_id": normalized_source_message_id,
            "client_request_id": normalized_request_id,
            "created_at": _utc_now(),
            "decided_at": None,
            "decided_by": None,
            "decision_reason": None,
        }
        records.append(proposal)
        _write_records(path, records)
        return _copy_record(proposal), True


def list_proposals(
    *,
    user_id: str | None,
    status: ProposalStatus | None = None,
) -> list[dict[str, Any]]:
    """List current proposal records, newest first, for one user namespace."""
    normalized_user_id = normalize_user_id(user_id)
    if status is not None:
        _validate_choice(status, name="status", allowed=_VALID_STATUSES)
    with _STORE_LOCK:
        records = _read_records(proposals_path(normalized_user_id))
    if status is not None:
        records = [record for record in records if record.get("status") == status]
    return [_copy_record(record) for record in reversed(records)]


def list_approved_memories(
    *,
    user_id: str | None,
    agent_id: str = DEFAULT_AGENT_ID,
    limit: int = MAX_BOOTSTRAP_MEMORIES,
) -> list[dict[str, Any]]:
    """Return the bounded active-memory set used during the next bootstrap."""
    if limit <= 0:
        return []
    approved = [
        record
        for record in list_proposals(user_id=user_id, status="approved")
        if is_memory_visible_to_agent(record, agent_id)
    ]
    return list(reversed(approved[:limit]))


def _format_materialized_layer(title: str, records: list[dict[str, Any]]) -> str:
    lines = [
        f"# {title}",
        "",
        "> Generated from approved memory proposals. Review changes through the memory API.",
        "",
    ]
    if not records:
        lines.append("No approved entries yet.")
        return "\n".join(lines) + "\n"

    for record in records:
        lines.extend(
            [
                f"## {record['proposal_id']}",
                "",
                str(record["content"]),
                "",
                "Provenance:",
                f"- type: {record['memory_type']}",
                f"- scope: {record['scope']}",
                f"- visibility: {record.get('visibility') or ('agent_private' if record['target'] in _PRIVATE_TARGETS else 'shared')}",
                f"- agent_id: {_record_owner(record) or 'shared'}",
                f"- source_session_id: {record.get('session_id') or 'unknown'}",
                f"- source_message_id: {record.get('source_message_id') or 'unknown'}",
                f"- rationale: {record['rationale']}",
                f"- approved_at: {record.get('decided_at') or 'unknown'}",
                f"- approved_by: {record.get('decided_by') or 'unknown'}",
                "",
            ]
        )
    return "\n".join(lines)


def materialize_approved_memories(*, user_id: str | None) -> dict[str, Path]:
    """Regenerate human-readable, provenance-preserving approved-memory layers.

    JSONL remains the append-safe audit source of truth; these files are a
    deterministic projection suitable for inspection today and MCP wrapping
    later. Regeneration prevents direct file edits from becoming active memory.
    """
    normalized_user_id = normalize_user_id(user_id)
    with _STORE_LOCK:
        records = _read_records(proposals_path(normalized_user_id))
        staging = _stage_projection(user_id=normalized_user_id, records=records)
        target = materialized_memory_dir(normalized_user_id)
        backup: Path | None = None
        try:
            backup = _activate_projection(staging=staging, target=target)
        except Exception:
            _remove_directory(staging)
            raise
        _remove_directory(backup)
        return materialized_memory_paths(normalized_user_id)


def _known_memory_user_ids() -> list[str]:
    user_ids = {DEFAULT_USER_ID}
    try:
        user_directories = list(user_state.DATA_USERS_DIR.iterdir())
    except OSError:
        user_directories = []
    for directory in user_directories:
        if not directory.is_dir():
            continue
        try:
            user_ids.add(normalize_user_id(directory.name))
        except ValueError:
            continue
    return sorted(user_ids)


def _remove_stale_transaction_artifacts(memory_dir: Path) -> None:
    for pattern in (
        f".{MATERIALIZED_DIRNAME}.stage-*",
        f".{MATERIALIZED_DIRNAME}.backup-*",
    ):
        for artifact in memory_dir.glob(pattern):
            _remove_directory(artifact)
    for artifact in memory_dir.glob(f".{PROPOSALS_FILENAME}.stage-*"):
        if artifact.is_dir():
            _remove_directory(artifact)
        else:
            artifact.unlink(missing_ok=True)


def recover_memory_projections() -> dict[str, dict[str, Path]]:
    """Repair interrupted projection transactions from JSONL on service startup.

    The JSONL proposal store is authoritative. Any leftover staging or backup
    path is discarded, then the approved-memory projection is regenerated for
    every user namespace that has persisted memory state.
    """
    recovered: dict[str, dict[str, Path]] = {}
    with _STORE_LOCK:
        for user_id in _known_memory_user_ids():
            memory_dir = _memory_dir_for_user(user_id)
            has_persisted_state = (
                proposals_path(user_id).exists()
                or materialized_memory_dir(user_id).exists()
                or any(memory_dir.glob(f".{MATERIALIZED_DIRNAME}.*"))
                or any(memory_dir.glob(f".{PROPOSALS_FILENAME}.stage-*"))
            )
            if not has_persisted_state:
                continue
            _remove_stale_transaction_artifacts(memory_dir)
            recovered[user_id] = materialize_approved_memories(user_id=user_id)
    return recovered


def _materialize_records(
    *,
    user_id: str,
    records: list[dict[str, Any]],
    output_dir: Path | None = None,
) -> dict[str, Path]:
    approved_records = [record for record in records if record.get("status") == "approved"]
    directory = output_dir or materialized_memory_dir(user_id)
    default_paths = _materialized_memory_paths_for_dir(directory)
    for target in _LAYER_METADATA:
        if target in _PRIVATE_TARGETS:
            continue
        path = default_paths[target]
        _, title = _LAYER_METADATA[target]
        target_records = [record for record in approved_records if record.get("target") == target]
        _write_records_as_markdown(path, _format_materialized_layer(title, target_records))

    for profile in list_agent_profiles():
        paths = _materialized_memory_paths_for_dir(directory, agent_id=profile.agent_id)
        for target in _PRIVATE_TARGETS:
            _, title = _LAYER_METADATA[target]
            target_records = [
                record
                for record in approved_records
                if record.get("target") == target and _record_owner(record) == profile.agent_id
            ]
            _write_records_as_markdown(
                paths[target],
                _format_materialized_layer(f"{title} · {profile.display_name}", target_records),
            )
    return default_paths


def _stage_projection(*, user_id: str, records: list[dict[str, Any]]) -> Path:
    target = materialized_memory_dir(user_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.with_name(f".{target.name}.stage-{uuid.uuid4().hex}")
    try:
        _materialize_records(user_id=user_id, records=records, output_dir=staging)
    except Exception:
        _remove_directory(staging)
        raise
    return staging


def _activate_projection(*, staging: Path, target: Path) -> Path | None:
    backup = target.with_name(f".{target.name}.backup-{uuid.uuid4().hex}")
    had_existing_projection = target.exists()
    if had_existing_projection:
        target.replace(backup)
    try:
        staging.replace(target)
    except Exception:
        if had_existing_projection:
            backup.replace(target)
        raise
    return backup if had_existing_projection else None


def _restore_projection(*, target: Path, backup: Path | None) -> None:
    _remove_directory(target)
    if backup is not None and backup.exists():
        backup.replace(target)


def _remove_directory(path: Path | None) -> None:
    if path is not None and path.exists():
        shutil.rmtree(path)


def _write_records_as_markdown(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(content, encoding="utf-8")
    temporary_path.replace(path)


def decide_proposal(
    *,
    user_id: str | None,
    proposal_id: str,
    decision: Literal["approved", "rejected"],
    decided_by: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Approve or reject one pending proposal and persist its state transition."""
    normalized_user_id = normalize_user_id(user_id)
    _validate_choice(decision, name="decision", allowed={"approved", "rejected"})
    normalized_reason = _optional_text(reason, name="reason", limit=1_000)
    path = proposals_path(normalized_user_id)

    with _STORE_LOCK:
        records = _read_records(path)
        for record in records:
            if record.get("proposal_id") != proposal_id:
                continue
            if record.get("status") != "pending":
                raise ProposalStateError(
                    f"proposal {proposal_id} is already {record.get('status', 'unknown')}"
                )
            record["status"] = decision
            record["decided_at"] = _utc_now()
            record["decided_by"] = normalize_user_id(decided_by or normalized_user_id)
            record["decision_reason"] = normalized_reason
            if decision == "approved":
                projection_staging = _stage_projection(
                    user_id=normalized_user_id,
                    records=records,
                )
                records_staging: Path | None = None
                projection_target = materialized_memory_dir(normalized_user_id)
                projection_backup: Path | None = None
                projection_active = False
                try:
                    records_staging = _stage_records(path, records)
                    projection_backup = _activate_projection(
                        staging=projection_staging,
                        target=projection_target,
                    )
                    projection_active = True
                    _commit_staged_records(records_staging, path)
                except Exception:
                    if projection_active:
                        _restore_projection(
                            target=projection_target,
                            backup=projection_backup,
                        )
                    _remove_directory(projection_staging)
                    if records_staging is not None:
                        records_staging.unlink(missing_ok=True)
                    raise
                _remove_directory(projection_backup)
            else:
                _write_records(path, records)
            return _copy_record(record)

    raise ProposalNotFoundError(f"proposal {proposal_id} was not found")


__all__ = [
    "MEMORY_DIR",
    "MAX_BOOTSTRAP_MEMORIES",
    "PROPOSALS_FILENAME",
    "ProposalNotFoundError",
    "ProposalStateError",
    "create_proposal",
    "decide_proposal",
    "is_memory_visible_to_agent",
    "list_approved_memories",
    "list_proposals",
    "materialize_approved_memories",
    "materialized_memory_dir",
    "materialized_memory_paths",
    "proposals_path",
    "recover_memory_projections",
]
