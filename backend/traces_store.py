"""Structured trace persistence for Mini-OpenClaw chat runs."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT: Path = Path(__file__).resolve().parents[1]
TRACES_DIR: Path = PROJECT_ROOT / "backend" / "data" / "traces"


def new_trace_id() -> str:
    return f"trace_{uuid.uuid4().hex}"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def trace_path(trace_id: str) -> Path:
    return TRACES_DIR / f"{trace_id}.json"


def create_trace(
    *,
    session_id: str,
    model_name: str,
    user_id: str | None = None,
    selected_agent_id: str | None = None,
    route_reason: str | None = None,
) -> dict[str, Any]:
    return {
        "trace_id": new_trace_id(),
        "session_id": session_id,
        "user_id": user_id,
        "selected_agent_id": selected_agent_id,
        "active_agent_id": selected_agent_id,
        "route_reason": route_reason,
        "handoff_count": 0,
        "start_time": utc_now_iso(),
        "end_time": None,
        "latency_ms": None,
        "model_name": model_name,
        "tool_calls": [],
        "tool_failures": [],
        "final_status": "running",
        "token_usage": None,
        "events": [],
        "error_category": None,
        "error_message": None,
        "friendly_message": None,
        "recoverable": None,
        "retry_count": 0,
        "graph_retrieval": None,
    }


def append_event(trace: dict[str, Any], *, kind: str, payload: dict[str, Any]) -> None:
    trace.setdefault("events", []).append(
        {
            "timestamp": utc_now_iso(),
            "kind": kind,
            "payload": payload,
        }
    )
    if kind == "tool_call":
        trace.setdefault("tool_calls", []).append(payload)
    if kind == "tool_result" and payload.get("name") == "agent_error":
        trace.setdefault("tool_failures", []).append(payload)


def record_error(
    trace: dict[str, Any],
    *,
    category: str,
    detail: str,
    friendly_message: str,
    recoverable: bool,
) -> None:
    trace["error_category"] = category
    trace["error_message"] = detail
    trace["friendly_message"] = friendly_message
    trace["recoverable"] = recoverable


def finalize_trace(
    trace: dict[str, Any],
    *,
    final_status: str,
    token_usage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    end_time = datetime.now(timezone.utc)
    start_time = datetime.fromisoformat(str(trace["start_time"]))
    trace["end_time"] = end_time.isoformat()
    trace["latency_ms"] = round((end_time - start_time).total_seconds() * 1000, 2)
    trace["final_status"] = final_status
    trace["token_usage"] = token_usage
    return trace


def save_trace(trace: dict[str, Any]) -> Path:
    TRACES_DIR.mkdir(parents=True, exist_ok=True)
    path = trace_path(str(trace["trace_id"]))
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def load_trace(trace_id: str) -> dict[str, Any] | None:
    path = trace_path(trace_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


__all__ = [
    "TRACES_DIR",
    "append_event",
    "create_trace",
    "finalize_trace",
    "load_trace",
    "new_trace_id",
    "save_trace",
]
