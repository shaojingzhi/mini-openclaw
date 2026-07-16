"""Background eval job helpers for Mini-OpenClaw."""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from backend.evals.runner import (
    DEFAULT_DATASET_PATH,
    DEFAULT_PROFILES_PATH,
    generate_eval_report,
)

EvalJobStatus = Literal["queued", "running", "completed", "failed"]

_EVAL_JOB_LOCK = threading.Lock()
_EVAL_JOBS: dict[str, dict[str, Any]] = {}
_EVAL_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mini-openclaw-evals")


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _coerce_path(value: str | Path | None, default: Path) -> str:
    if value is None:
        return str(default)
    return str(Path(value))


def _serialize_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "output": str(result["output"]),
        "markdown_output": str(result["markdown_output"]),
        "dataset_size": int(result["dataset_size"]),
        "profiles": list(result.get("profiles", [])),
        "langsmith_sync": result.get("langsmith_sync"),
    }


def _copy_job(job: dict[str, Any]) -> dict[str, Any]:
    return {
        **job,
        "request": dict(job["request"]),
        "result": dict(job["result"]) if isinstance(job.get("result"), dict) else None,
    }


def _update_job(job_id: str, **changes: Any) -> None:
    with _EVAL_JOB_LOCK:
        job = _EVAL_JOBS.get(job_id)
        if job is None:
            return
        job.update(changes)
        job["updated_at"] = _utc_now()


def _run_eval_job(
    job_id: str,
    *,
    dataset_path: str,
    profiles_path: str,
    profile_ids: list[str] | None,
    sync_langsmith: bool,
) -> None:
    _update_job(job_id, status="running")
    try:
        result = generate_eval_report(
            dataset_path=dataset_path,
            profiles_path=profiles_path,
            profile_ids=profile_ids,
            sync_langsmith=sync_langsmith,
        )
        _update_job(job_id, status="completed", result=_serialize_result(result), error=None)
    except Exception as exc:
        _update_job(job_id, status="failed", error=f"{type(exc).__name__}: {exc}")


def submit_eval_job(
    *,
    dataset_path: str | Path | None = None,
    profiles_path: str | Path | None = None,
    profile_ids: list[str] | None = None,
    sync_langsmith: bool = False,
) -> dict[str, Any]:
    job_id = f"eval_{uuid.uuid4().hex[:12]}"
    request_payload = {
        "dataset_path": _coerce_path(dataset_path, DEFAULT_DATASET_PATH),
        "profiles_path": _coerce_path(profiles_path, DEFAULT_PROFILES_PATH),
        "profile_ids": list(profile_ids) if profile_ids is not None else None,
        "sync_langsmith": sync_langsmith,
    }
    job = {
        "job_id": job_id,
        "status": "queued",
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "request": request_payload,
        "result": None,
        "error": None,
    }
    with _EVAL_JOB_LOCK:
        _EVAL_JOBS[job_id] = job
    _EVAL_EXECUTOR.submit(
        _run_eval_job,
        job_id,
        dataset_path=request_payload["dataset_path"],
        profiles_path=request_payload["profiles_path"],
        profile_ids=request_payload["profile_ids"],
        sync_langsmith=sync_langsmith,
    )
    return _copy_job(job)


def get_eval_job(job_id: str) -> dict[str, Any] | None:
    with _EVAL_JOB_LOCK:
        job = _EVAL_JOBS.get(job_id)
        return _copy_job(job) if job is not None else None


__all__ = ["EvalJobStatus", "get_eval_job", "submit_eval_job"]
