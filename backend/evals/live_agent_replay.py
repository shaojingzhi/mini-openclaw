"""Replay core eval tasks through Mini-OpenClaw's product chat pipeline.

This runner deliberately measures tool-contract behavior, not semantic answer
quality: a task passes only when it completes, emits non-empty output, and
observes every tool declared by the task. The product's SSE path is reused so
the report is derived from real model/tool events rather than task tags.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import uuid
from collections import Counter
from pathlib import Path
from statistics import fmean
from typing import Any, AsyncIterator, Callable

from backend.evals.runner import DEFAULT_DATASET_PATH, EvaluationTask, load_dataset

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = PROJECT_ROOT / "backend" / "evals" / "reports" / "live_agent_replay.json"
StreamRunner = Callable[
    [str, str, str, str | None, str | None, str | None],
    AsyncIterator[dict[str, str]],
]


async def _stream_product_chat(
    message: str,
    session_id: str,
    user_id: str,
    api_key: str | None,
    base_url: str | None,
    model: str | None,
) -> AsyncIterator[dict[str, str]]:
    # Import lazily so dataset-only workflows do not pull in the FastAPI app.
    from backend.app import ChatRequest, _chat_sse

    request = ChatRequest(
        message=message,
        session_id=session_id,
        stream=True,
        api_key=api_key,
        base_url=base_url,
        model=model,
    )
    async for event in _chat_sse(request, user_id=user_id):
        yield event


def _decode_event(event: dict[str, str]) -> tuple[str, dict[str, Any]]:
    kind = str(event.get("event") or "")
    raw_data = event.get("data", "{}")
    try:
        payload = json.loads(raw_data)
    except (TypeError, json.JSONDecodeError):
        payload = {"content": str(raw_data)}
    return kind, payload if isinstance(payload, dict) else {"content": str(payload)}


async def _replay_task(
    task: EvaluationTask,
    *,
    user_id: str,
    session_prefix: str,
    api_key: str | None,
    base_url: str | None,
    model: str | None,
    stream_runner: StreamRunner,
) -> dict[str, Any]:
    session_id = f"{session_prefix}-{task.session_id or task.id}"
    turns = task.turns or [task.prompt]
    started = time.perf_counter()
    tool_calls: list[str] = []
    tool_results: list[str] = []
    final_texts: list[str] = []
    error_categories: list[str] = []

    for message in turns:
        async for event in stream_runner(message, session_id, user_id, api_key, base_url, model):
            kind, payload = _decode_event(event)
            if kind == "tool_call":
                tool_calls.append(str(payload.get("name") or "tool"))
            elif kind == "tool_result":
                name = str(payload.get("name") or "tool")
                tool_results.append(name)
                if name == "agent_error":
                    error_categories.append(str(payload.get("category") or "agent_error"))
            elif kind == "final":
                content = str(payload.get("content") or "").strip()
                if content:
                    final_texts.append(content)

    observed_tools = sorted(set(tool_calls))
    missing_tools = sorted(set(task.required_tools) - set(observed_tools))
    completed = bool(final_texts) and not error_categories
    required_tools_observed = not missing_tools
    return {
        "task_id": task.id,
        "category": task.category,
        "session_id": session_id,
        "turn_count": len(turns),
        "task_contract_passed": completed and required_tools_observed,
        "response_completed": completed,
        "required_tools": task.required_tools,
        "observed_tools": observed_tools,
        "missing_required_tools": missing_tools,
        "tool_call_count": len(tool_calls),
        "tool_result_count": len(tool_results),
        "tool_result_observation_rate": round(len(tool_results) / len(tool_calls), 4)
        if tool_calls
        else None,
        "error_categories": error_categories,
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        "final_response_preview": final_texts[-1][:300] if final_texts else "",
    }


async def run_live_agent_replay_async(
    tasks: list[EvaluationTask],
    *,
    user_id: str | None = None,
    session_prefix: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    stream_runner: StreamRunner = _stream_product_chat,
) -> dict[str, Any]:
    run_id = uuid.uuid4().hex[:12]
    active_user_id = user_id or f"eval-{run_id}"
    active_prefix = session_prefix or f"live-eval-{run_id}"
    results = [
        await _replay_task(
            task,
            user_id=active_user_id,
            session_prefix=active_prefix,
            api_key=api_key,
            base_url=base_url,
            model=model,
            stream_runner=stream_runner,
        )
        for task in tasks
    ]
    total_required_tools = sum(len(task.required_tools) for task in tasks)
    observed_required_tools = sum(
        len(set(row["required_tools"]) & set(row["observed_tools"])) for row in results
    )
    category_breakdown: dict[str, dict[str, int | float]] = {}
    for category in sorted({task.category for task in tasks}):
        rows = [row for row in results if row["category"] == category]
        category_breakdown[category] = {
            "case_count": len(rows),
            "task_contract_pass_rate": round(
                sum(bool(row["task_contract_passed"]) for row in rows) / len(rows), 4
            ),
        }
    return {
        "execution_mode": "live_product_agent_replay",
        "evaluation_scope": "tool_contract_only; semantic answer correctness requires separate judging",
        "run_id": run_id,
        "user_id": active_user_id,
        "session_prefix": active_prefix,
        "dataset_size": len(tasks),
        "model_override": model,
        "metrics": {
            "task_contract_pass_rate": round(
                sum(bool(row["task_contract_passed"]) for row in results) / len(results), 4
            ) if results else 0.0,
            "response_completion_rate": round(
                sum(bool(row["response_completed"]) for row in results) / len(results), 4
            ) if results else 0.0,
            "required_tool_coverage_rate": round(observed_required_tools / total_required_tools, 4)
            if total_required_tools
            else 1.0,
            "tool_result_observation_rate": round(
                sum(row["tool_result_count"] for row in results)
                / sum(row["tool_call_count"] for row in results),
                4,
            ) if sum(row["tool_call_count"] for row in results) else 1.0,
            "average_latency_ms": round(fmean(row["latency_ms"] for row in results), 2)
            if results
            else 0.0,
        },
        "category_breakdown": category_breakdown,
        "failure_categories": dict(
            sorted(Counter(category for row in results for category in row["error_categories"]).items())
        ),
        "results": results,
    }


def run_live_agent_replay(tasks: list[EvaluationTask], **kwargs: Any) -> dict[str, Any]:
    return asyncio.run(run_live_agent_replay_async(tasks, **kwargs))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay eval tasks through the live Mini-OpenClaw agent")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET_PATH))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    tasks = load_dataset(args.dataset)
    if args.limit is not None:
        tasks = tasks[: args.limit]
    report = run_live_agent_replay(
        tasks,
        api_key=args.api_key,
        base_url=args.base_url,
        model=args.model,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["metrics"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
