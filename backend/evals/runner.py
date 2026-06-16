"""Offline evaluation runner for Mini-OpenClaw.

Usage:
    python -m backend.evals.runner --dataset backend/evals/datasets/core_tasks.json --output backend/evals/reports/latest.json
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import fmean
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET_PATH = PROJECT_ROOT / "backend" / "evals" / "datasets" / "core_tasks.json"


@dataclass(frozen=True)
class EvaluationTask:
    id: str
    category: str
    prompt: str
    expected: str
    tags: list[str]
    required_tools: list[str]
    session_id: str | None = None
    turns: list[str] | None = None


@dataclass(frozen=True)
class RunResult:
    task_id: str
    category: str
    success: bool
    latency_ms: float
    tool_calls: int
    tool_successes: int
    tool_failures: int
    failure_category: str | None
    notes: str = ""


def load_dataset(path: str | Path = DEFAULT_DATASET_PATH) -> list[EvaluationTask]:
    dataset_path = Path(path)
    raw = json.loads(dataset_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("evaluation dataset must be a JSON array")

    tasks: list[EvaluationTask] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("each evaluation task must be a JSON object")
        tasks.append(
            EvaluationTask(
                id=str(item["id"]),
                category=str(item["category"]),
                prompt=str(item["prompt"]),
                expected=str(item["expected"]),
                tags=[str(tag) for tag in item.get("tags", [])],
                required_tools=[str(tool) for tool in item.get("required_tools", [])],
                session_id=str(item["session_id"]) if item.get("session_id") else None,
                turns=[str(turn) for turn in item.get("turns", [])] or None,
            )
        )
    return tasks


Evaluator = Callable[[EvaluationTask], RunResult]


def _default_stub_evaluator(task: EvaluationTask) -> RunResult:
    start = time.perf_counter()
    latency_ms = max((time.perf_counter() - start) * 1000, 1.0)
    return RunResult(
        task_id=task.id,
        category=task.category,
        success=False,
        latency_ms=latency_ms,
        tool_calls=len(task.required_tools),
        tool_successes=0,
        tool_failures=len(task.required_tools),
        failure_category="not_executed",
        notes="No live evaluator was provided; this is a dry-run dataset validation.",
    )


def run_dataset(
    tasks: list[EvaluationTask],
    *,
    evaluator: Evaluator | None = None,
) -> dict[str, Any]:
    runner = evaluator or _default_stub_evaluator
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    results = [runner(task) for task in tasks]
    report = aggregate_report(tasks, results)
    report["started_at"] = started_at
    report["dataset_size"] = len(tasks)
    report["tasks"] = [asdict(task) for task in tasks]
    report["results"] = [asdict(result) for result in results]
    return report


def aggregate_report(
    tasks: list[EvaluationTask],
    results: list[RunResult],
) -> dict[str, Any]:
    if len(tasks) != len(results):
        raise ValueError("tasks and results must have the same length")

    total_tasks = len(results)
    if total_tasks == 0:
        return {
            "task_success_rate": 0.0,
            "tool_call_success_rate": 0.0,
            "average_latency_ms": 0.0,
            "average_tool_calls": 0.0,
            "failure_category_distribution": {},
            "category_breakdown": {},
        }

    success_count = sum(1 for result in results if result.success)
    total_tool_calls = sum(result.tool_calls for result in results)
    total_tool_successes = sum(result.tool_successes for result in results)
    failure_counter = Counter(
        result.failure_category for result in results if result.failure_category
    )

    category_breakdown: dict[str, dict[str, float | int]] = {}
    for category in sorted({task.category for task in tasks}):
        category_results = [result for result in results if result.category == category]
        category_breakdown[category] = {
            "count": len(category_results),
            "success_rate": round(
                sum(1 for result in category_results if result.success)
                / len(category_results),
                4,
            ) if category_results else 0.0,
        }

    return {
        "task_success_rate": round(success_count / total_tasks, 4),
        "tool_call_success_rate": round(
            total_tool_successes / total_tool_calls,
            4,
        ) if total_tool_calls else 0.0,
        "average_latency_ms": round(fmean(result.latency_ms for result in results), 2),
        "average_tool_calls": round(total_tool_calls / total_tasks, 2),
        "failure_category_distribution": dict(sorted(failure_counter.items())),
        "category_breakdown": category_breakdown,
    }


def write_report(report: dict[str, Any], output_path: str | Path) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Mini-OpenClaw offline evals")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET_PATH))
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    tasks = load_dataset(args.dataset)
    report = run_dataset(tasks)
    output = write_report(report, args.output)
    print(json.dumps({"output": str(output), "dataset_size": len(tasks)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
