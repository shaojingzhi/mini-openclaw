"""Offline evaluation runner for Mini-OpenClaw.

Usage:
    python -m backend.evals.runner --dataset backend/evals/datasets/core_tasks.json --output backend/evals/reports/latest.json
"""

from __future__ import annotations

import argparse
import inspect
import json
import time
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import fmean
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET_PATH = PROJECT_ROOT / "backend" / "evals" / "datasets" / "core_tasks.json"
DEFAULT_PROFILES_PATH = PROJECT_ROOT / "backend" / "evals" / "profiles.json"


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
class EvalProfile:
    id: str
    description: str
    disabled_capabilities: list[str]


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


def load_profiles(path: str | Path = DEFAULT_PROFILES_PATH) -> list[EvalProfile]:
    profiles_path = Path(path)
    raw = json.loads(profiles_path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        raw = raw.get("profiles", [])
    if not isinstance(raw, list):
        raise ValueError("evaluation profiles must be a JSON array or {profiles: [...]}")

    profiles: list[EvalProfile] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("each evaluation profile must be a JSON object")
        profiles.append(
            EvalProfile(
                id=str(item["id"]),
                description=str(item.get("description", "")),
                disabled_capabilities=[
                    str(value) for value in item.get("disabled_capabilities", [])
                ],
            )
        )
    return profiles


def select_profiles(
    profiles: list[EvalProfile],
    requested_ids: list[str] | None = None,
) -> list[EvalProfile]:
    if not requested_ids:
        return profiles

    profile_map = {profile.id: profile for profile in profiles}
    selected: list[EvalProfile] = []
    missing: list[str] = []
    for profile_id in requested_ids:
        profile = profile_map.get(profile_id)
        if profile is None:
            missing.append(profile_id)
            continue
        selected.append(profile)

    if missing:
        raise ValueError(f"unknown eval profiles: {', '.join(missing)}")
    return selected


Evaluator = Callable[..., RunResult]


def _task_uses_capability(task: EvaluationTask, capability: str) -> bool:
    capability_aliases = {
        "memory": {"memory", "session", "multi_turn_context"},
        "skills": {"skills"},
        "retrieval": {"knowledge", "knowledge_retrieval"},
    }
    aliases = capability_aliases.get(capability, {capability})
    haystack = set(task.tags)
    haystack.add(task.category)
    return any(alias in haystack for alias in aliases)


def _default_stub_evaluator(task: EvaluationTask, profile: EvalProfile) -> RunResult:
    blocked_capability = next(
        (
            capability
            for capability in profile.disabled_capabilities
            if _task_uses_capability(task, capability)
        ),
        None,
    )
    latency_ms = float(
        75 + (len(task.required_tools) * 15) + (len(profile.disabled_capabilities) * 10)
    )
    if blocked_capability is not None:
        return RunResult(
            task_id=task.id,
            category=task.category,
            success=False,
            latency_ms=latency_ms,
            tool_calls=len(task.required_tools),
            tool_successes=0,
            tool_failures=len(task.required_tools),
            failure_category="ablation_disabled",
            notes=f"Synthetic eval: blocked by profile capability '{blocked_capability}'.",
        )

    return RunResult(
        task_id=task.id,
        category=task.category,
        success=True,
        latency_ms=latency_ms,
        tool_calls=len(task.required_tools),
        tool_successes=len(task.required_tools),
        tool_failures=0,
        failure_category=None,
        notes="Synthetic eval: passed capability contract check for this profile.",
    )


def run_dataset(
    tasks: list[EvaluationTask],
    *,
    profile: EvalProfile | None = None,
    evaluator: Evaluator | None = None,
) -> dict[str, Any]:
    active_profile = profile or EvalProfile(
        id="baseline",
        description="Full capability baseline.",
        disabled_capabilities=[],
    )
    runner = evaluator or _default_stub_evaluator
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    results = [_run_task_with_profile(runner, task, active_profile) for task in tasks]
    report = aggregate_report(tasks, results)
    report["profile_id"] = active_profile.id
    report["profile_description"] = active_profile.description
    report["disabled_capabilities"] = active_profile.disabled_capabilities
    report["execution_mode"] = (
        "custom_evaluator" if evaluator is not None else "synthetic_profile_check"
    )
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


def run_profiles(
    tasks: list[EvaluationTask],
    profiles: list[EvalProfile],
    *,
    evaluator: Evaluator | None = None,
) -> dict[str, Any]:
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    profile_reports = [
        run_dataset(tasks, profile=profile, evaluator=evaluator) for profile in profiles
    ]
    return {
        "started_at": started_at,
        "dataset_size": len(tasks),
        "profile_ids": [profile.id for profile in profiles],
        "execution_mode": (
            "custom_evaluator" if evaluator is not None else "synthetic_profile_check"
        ),
        "profiles": profile_reports,
        "ablation_comparison": build_ablation_comparison(profile_reports),
    }


def build_ablation_comparison(
    profile_reports: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not profile_reports:
        return []

    baseline = profile_reports[0]
    baseline_id = str(baseline["profile_id"])
    comparison: list[dict[str, Any]] = []
    for report in profile_reports[1:]:
        comparison.append(
            {
                "baseline": baseline_id,
                "candidate": str(report["profile_id"]),
                "task_success_delta": round(
                    float(report["task_success_rate"])
                    - float(baseline["task_success_rate"]),
                    4,
                ),
                "tool_call_success_delta": round(
                    float(report["tool_call_success_rate"])
                    - float(baseline["tool_call_success_rate"]),
                    4,
                ),
                "average_latency_delta_ms": round(
                    float(report["average_latency_ms"])
                    - float(baseline["average_latency_ms"]),
                    2,
                ),
            }
        )
    return comparison


def write_report(report: dict[str, Any], output_path: str | Path) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def render_markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# Mini-OpenClaw Evaluation Report",
        "",
        f"- Dataset size: {report.get('dataset_size', 0)}",
        f"- Execution mode: {report.get('execution_mode', 'unknown')}",
        f"- Profiles: {', '.join(report.get('profile_ids', [])) or 'none'}",
        "",
        "## Profile Summary",
        "",
        "| Profile | Disabled Capabilities | Task Success | Tool Call Success | Avg Latency (ms) | Avg Tool Calls |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for profile in report.get("profiles", []):
        disabled = ", ".join(profile.get("disabled_capabilities", [])) or "none"
        lines.append(
            "| "
            f"{profile.get('profile_id', 'unknown')} | "
            f"{disabled} | "
            f"{profile.get('task_success_rate', 0.0):.4f} | "
            f"{profile.get('tool_call_success_rate', 0.0):.4f} | "
            f"{profile.get('average_latency_ms', 0.0):.2f} | "
            f"{profile.get('average_tool_calls', 0.0):.2f} |"
        )

    comparison = report.get("ablation_comparison", [])
    if comparison:
        lines.extend(
            [
                "",
                "## Ablation Comparison vs Baseline",
                "",
                "| Candidate | Task Success Δ | Tool Call Success Δ | Avg Latency Δ (ms) |",
                "| --- | ---: | ---: | ---: |",
            ]
        )
        for row in comparison:
            lines.append(
                "| "
                f"{row.get('candidate', 'unknown')} | "
                f"{float(row.get('task_success_delta', 0.0)):+.4f} | "
                f"{float(row.get('tool_call_success_delta', 0.0)):+.4f} | "
                f"{float(row.get('average_latency_delta_ms', 0.0)):+.2f} |"
            )

    lines.append("")
    return "\n".join(lines)


def write_markdown_report(report: dict[str, Any], output_path: str | Path) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_markdown_report(report), encoding="utf-8")
    return target


def _run_task_with_profile(
    evaluator: Evaluator,
    task: EvaluationTask,
    profile: EvalProfile,
) -> RunResult:
    params = inspect.signature(evaluator).parameters
    if len(params) >= 2:
        return evaluator(task, profile)
    return evaluator(task)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Mini-OpenClaw offline evals")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET_PATH))
    parser.add_argument("--profiles", default=str(DEFAULT_PROFILES_PATH))
    parser.add_argument("--profile", action="append", dest="profile_ids")
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    tasks = load_dataset(args.dataset)
    profiles = select_profiles(load_profiles(args.profiles), args.profile_ids)
    report = run_profiles(tasks, profiles)
    output = write_report(report, args.output)
    markdown_output = write_markdown_report(report, Path(args.output).with_suffix(".md"))
    print(
        json.dumps(
            {
                "output": str(output),
                "markdown_output": str(markdown_output),
                "dataset_size": len(tasks),
                "profiles": [profile.id for profile in profiles],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
