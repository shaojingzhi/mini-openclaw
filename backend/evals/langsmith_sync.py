"""LangSmith dataset sync helpers for Mini-OpenClaw evals."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from langsmith import Client

from backend.evals.runner import (
    DEFAULT_DATASET_PATH,
    DEFAULT_RETRIEVAL_EVAL_PATH,
    EvaluationTask,
    RetrievalEvalCase,
    load_dataset,
    load_retrieval_eval_dataset,
)
from backend.settings import get_settings

CORE_LANGSMITH_DATASET_NAME = "mini-openclaw-core-tasks"
RETRIEVAL_LANGSMITH_DATASET_NAME = "mini-openclaw-retrieval-quality"


@dataclass(frozen=True)
class LangSmithDatasetSyncResult:
    name: str
    status: str
    example_count: int
    dataset_id: str | None = None
    note: str = ""


def build_client() -> Client | None:
    settings = get_settings()
    if not settings.langsmith_api_key:
        return None
    try:
        return Client(
            api_url=settings.langsmith_endpoint,
            api_key=settings.langsmith_api_key,
        )
    except Exception:
        return None


def sync_local_datasets(
    client: Client | None = None,
    *,
    tasks_path: str | Path = DEFAULT_DATASET_PATH,
    retrieval_path: str | Path = DEFAULT_RETRIEVAL_EVAL_PATH,
) -> dict[str, Any]:
    """Upload the local eval datasets to LangSmith when configured."""
    active_client = client or build_client()
    settings = get_settings()
    if active_client is None:
        return {
            "enabled": False,
            "project_name": settings.langsmith_project,
            "reason": "LangSmith API key is not configured.",
            "datasets": [],
        }

    tasks = load_dataset(tasks_path)
    retrieval_path = Path(retrieval_path)
    retrieval_cases = (
        load_retrieval_eval_dataset(retrieval_path) if retrieval_path.exists() else []
    )

    datasets = [
        _sync_tasks_dataset(active_client, tasks),
        _sync_retrieval_dataset(active_client, retrieval_cases),
    ]
    return {
        "enabled": True,
        "project_name": settings.langsmith_project,
        "reason": "",
        "datasets": [asdict(result) for result in datasets],
    }


def _sync_tasks_dataset(
    client: Client,
    tasks: list[EvaluationTask],
) -> LangSmithDatasetSyncResult:
    examples = [_task_to_example(task) for task in tasks]
    return _sync_dataset(
        client,
        dataset_name=CORE_LANGSMITH_DATASET_NAME,
        description="Mini-OpenClaw core capability eval tasks.",
        examples=examples,
        inputs_schema={
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "category": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "required_tools": {"type": "array", "items": {"type": "string"}},
                "session_id": {"type": ["string", "null"]},
                "turns": {"type": "array", "items": {"type": "string"}},
            },
        },
        outputs_schema={
            "type": "object",
            "properties": {
                "expected": {"type": "string"},
            },
        },
    )


def _sync_retrieval_dataset(
    client: Client,
    cases: list[RetrievalEvalCase],
) -> LangSmithDatasetSyncResult:
    examples = [_retrieval_case_to_example(case) for case in cases]
    return _sync_dataset(
        client,
        dataset_name=RETRIEVAL_LANGSMITH_DATASET_NAME,
        description="Mini-OpenClaw retrieval quality eval cases.",
        examples=examples,
        inputs_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
            },
        },
        outputs_schema={
            "type": "object",
            "properties": {
                "relevant_ids": {"type": "array", "items": {"type": "string"}},
            },
        },
    )


def _sync_dataset(
    client: Client,
    *,
    dataset_name: str,
    description: str,
    examples: list[dict[str, Any]],
    inputs_schema: dict[str, Any],
    outputs_schema: dict[str, Any],
) -> LangSmithDatasetSyncResult:
    try:
        if client.has_dataset(dataset_name):
            dataset = client.read_dataset(dataset_name=dataset_name)
            return LangSmithDatasetSyncResult(
                name=dataset_name,
                status="existing",
                example_count=int(dataset.example_count or 0),
                dataset_id=str(dataset.id),
                note="Dataset already exists in LangSmith.",
            )

        dataset = client.create_dataset(
            dataset_name=dataset_name,
            description=description,
            inputs_schema=inputs_schema,
            outputs_schema=outputs_schema,
            metadata={
                "source": "mini-openclaw",
            },
        )
        if examples:
            client.create_examples(dataset_id=dataset.id, examples=examples)
        return LangSmithDatasetSyncResult(
            name=dataset_name,
            status="created",
            example_count=len(examples),
            dataset_id=str(dataset.id),
        )
    except Exception as exc:
        return LangSmithDatasetSyncResult(
            name=dataset_name,
            status="skipped",
            example_count=0,
            note=f"{type(exc).__name__}: {exc}",
        )


def _task_to_example(task: EvaluationTask) -> dict[str, Any]:
    return {
        "id": task.id,
        "inputs": {
            "prompt": task.prompt,
            "category": task.category,
            "tags": task.tags,
            "required_tools": task.required_tools,
            "session_id": task.session_id,
            "turns": task.turns or [],
        },
        "outputs": {"expected": task.expected},
        "metadata": {"task_id": task.id, "source": "core_tasks"},
    }


def _retrieval_case_to_example(case: RetrievalEvalCase) -> dict[str, Any]:
    return {
        "id": case.id,
        "inputs": {"query": case.query},
        "outputs": {"relevant_ids": case.relevant_ids},
        "metadata": {
            "case_id": case.id,
            "source": "retrieval_quality",
            "strategies": sorted(case.strategies.keys()),
        },
    }


__all__ = [
    "CORE_LANGSMITH_DATASET_NAME",
    "RETRIEVAL_LANGSMITH_DATASET_NAME",
    "LangSmithDatasetSyncResult",
    "build_client",
    "sync_local_datasets",
]
