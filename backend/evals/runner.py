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
from math import log2
from pathlib import Path
from statistics import fmean
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET_PATH = PROJECT_ROOT / "backend" / "evals" / "datasets" / "core_tasks.json"
DEFAULT_RETRIEVAL_EVAL_PATH = (
    PROJECT_ROOT / "backend" / "evals" / "datasets" / "retrieval_quality.json"
)
DEFAULT_PROFILES_PATH = PROJECT_ROOT / "backend" / "evals" / "profiles.json"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "backend" / "evals" / "reports" / "latest.json"


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


@dataclass(frozen=True)
class RetrievalEvalCase:
    id: str
    query: str
    relevant_ids: list[str]
    strategies: dict[str, list[str]]


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


def load_retrieval_eval_dataset(
    path: str | Path = DEFAULT_RETRIEVAL_EVAL_PATH,
) -> list[RetrievalEvalCase]:
    dataset_path = Path(path)
    raw = json.loads(dataset_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("retrieval eval dataset must be a JSON array")

    cases: list[RetrievalEvalCase] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("each retrieval eval case must be a JSON object")
        strategies = item.get("strategies", {})
        if not isinstance(strategies, dict):
            raise ValueError("retrieval eval case strategies must be an object")
        cases.append(
            RetrievalEvalCase(
                id=str(item["id"]),
                query=str(item["query"]),
                relevant_ids=[str(value) for value in item.get("relevant_ids", [])],
                strategies={
                    str(strategy): [str(value) for value in retrieved_ids]
                    for strategy, retrieved_ids in strategies.items()
                    if isinstance(retrieved_ids, list)
                },
            )
        )
    return cases


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
        "graph_retrieval": {
            "graph",
            "graph_assisted",
            "graph_retrieval",
            "multi_hop_retrieval",
        },
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


def compute_retrieval_metrics(
    retrieved_ids: list[str],
    relevant_ids: list[str],
    *,
    top_k: int = 5,
) -> dict[str, float | int]:
    if top_k <= 0:
        raise ValueError("top_k must be greater than zero")

    relevant = set(relevant_ids)
    top_results = retrieved_ids[:top_k]
    if not relevant:
        return {
            "top_k": top_k,
            "recall_at_k": 0.0,
            "mrr": 0.0,
            "hit_at_1": 0.0,
            "ndcg_at_k": 0.0,
        }

    seen_hits: set[str] = set()
    hit_count = 0
    first_hit_rank: int | None = None
    dcg = 0.0
    for rank, item_id in enumerate(top_results, start=1):
        if item_id not in relevant or item_id in seen_hits:
            continue
        seen_hits.add(item_id)
        hit_count += 1
        if first_hit_rank is None:
            first_hit_rank = rank
        dcg += 1 / log2(rank + 1)

    ideal_hits = min(len(relevant), top_k)
    ideal_dcg = sum(1 / log2(rank + 1) for rank in range(1, ideal_hits + 1))
    return {
        "top_k": top_k,
        "recall_at_k": round(hit_count / len(relevant), 4),
        "mrr": round(1 / first_hit_rank, 4) if first_hit_rank else 0.0,
        "hit_at_1": 1.0 if top_results and top_results[0] in relevant else 0.0,
        "ndcg_at_k": round(dcg / ideal_dcg, 4) if ideal_dcg else 0.0,
    }


def run_retrieval_evaluation(
    cases: list[RetrievalEvalCase],
    *,
    top_k: int = 5,
    baseline_strategy: str = "baseline",
) -> dict[str, Any]:
    strategy_order: list[str] = []
    rows: list[dict[str, Any]] = []
    for case in cases:
        for strategy, retrieved_ids in case.strategies.items():
            if strategy not in strategy_order:
                strategy_order.append(strategy)
            metrics = compute_retrieval_metrics(
                retrieved_ids,
                case.relevant_ids,
                top_k=top_k,
            )
            rows.append(
                {
                    "case_id": case.id,
                    "query": case.query,
                    "strategy": strategy,
                    "relevant_ids": case.relevant_ids,
                    "retrieved_ids": retrieved_ids,
                    "metrics": metrics,
                }
            )

    summary = _summarize_retrieval_rows(rows, strategy_order)
    return {
        "top_k": top_k,
        "case_count": len(cases),
        "strategies": strategy_order,
        "summary": summary,
        "comparison_vs_baseline": _compare_retrieval_strategies(
            summary,
            baseline_strategy=baseline_strategy,
        ),
        "cases": rows,
    }


def _summarize_retrieval_rows(
    rows: list[dict[str, Any]],
    strategy_order: list[str],
) -> dict[str, dict[str, float | int]]:
    summary: dict[str, dict[str, float | int]] = {}
    metric_names = ["recall_at_k", "mrr", "hit_at_1", "ndcg_at_k"]
    for strategy in strategy_order:
        strategy_rows = [row for row in rows if row["strategy"] == strategy]
        summary[strategy] = {"case_count": len(strategy_rows)}
        for metric_name in metric_names:
            values = [
                float(row["metrics"][metric_name])
                for row in strategy_rows
            ]
            summary[strategy][metric_name] = (
                round(fmean(values), 4) if values else 0.0
            )
    return summary


def _compare_retrieval_strategies(
    summary: dict[str, dict[str, float | int]],
    *,
    baseline_strategy: str,
) -> list[dict[str, Any]]:
    baseline = summary.get(baseline_strategy)
    if not baseline:
        return []

    metric_names = ["recall_at_k", "mrr", "hit_at_1", "ndcg_at_k"]
    comparison: list[dict[str, Any]] = []
    for strategy, metrics in summary.items():
        if strategy == baseline_strategy:
            continue
        row: dict[str, Any] = {
            "baseline": baseline_strategy,
            "candidate": strategy,
        }
        for metric_name in metric_names:
            row[f"{metric_name}_delta"] = round(
                float(metrics.get(metric_name, 0.0))
                - float(baseline.get(metric_name, 0.0)),
                4,
            )
        comparison.append(row)
    return comparison


def run_profiles(
    tasks: list[EvaluationTask],
    profiles: list[EvalProfile],
    *,
    evaluator: Evaluator | None = None,
    retrieval_cases: list[RetrievalEvalCase] | None = None,
    retrieval_top_k: int = 5,
) -> dict[str, Any]:
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    profile_reports = [
        run_dataset(tasks, profile=profile, evaluator=evaluator) for profile in profiles
    ]
    report: dict[str, Any] = {
        "started_at": started_at,
        "dataset_size": len(tasks),
        "profile_ids": [profile.id for profile in profiles],
        "execution_mode": (
            "custom_evaluator" if evaluator is not None else "synthetic_profile_check"
        ),
        "profiles": profile_reports,
        "ablation_comparison": build_ablation_comparison(profile_reports),
    }
    if retrieval_cases is not None:
        report["retrieval_quality"] = run_retrieval_evaluation(
            retrieval_cases,
            top_k=retrieval_top_k,
        )
    return report


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

    graph_rows = _graph_retrieval_rows(report)
    if graph_rows:
        lines.extend(
            [
                "",
                "## Graph-Assisted Retrieval Check",
                "",
                "Graph-assisted retrieval is most useful for multi-hop questions that need to connect knowledge docs, skills, workspace files, and traces. It is unnecessary for simple keyword lookups where the direct retrieval result already contains the answer.",
                "",
                "| Profile | Graph Tasks | Graph Success | Interpretation |",
                "| --- | ---: | ---: | --- |",
            ]
        )
        for row in graph_rows:
            lines.append(
                "| "
                f"{row['profile_id']} | "
                f"{row['task_count']} | "
                f"{row['success_rate']:.4f} | "
                f"{row['interpretation']} |"
            )

    retrieval_quality = report.get("retrieval_quality")
    if isinstance(retrieval_quality, dict):
        lines.extend(
            [
                "",
                "## Retrieval Quality Metrics",
                "",
                f"Offline labeled retrieval check at K={retrieval_quality.get('top_k', 5)}. These metrics make the Graph-RAG-inspired path measurable before it is wired into a live benchmark runner.",
                "",
                "| Strategy | Cases | Recall@K | MRR | Hit@1 | nDCG@K |",
                "| --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        summary = retrieval_quality.get("summary", {})
        if isinstance(summary, dict):
            for strategy, metrics in summary.items():
                if not isinstance(metrics, dict):
                    continue
                lines.append(
                    "| "
                    f"{strategy} | "
                    f"{int(metrics.get('case_count', 0))} | "
                    f"{float(metrics.get('recall_at_k', 0.0)):.4f} | "
                    f"{float(metrics.get('mrr', 0.0)):.4f} | "
                    f"{float(metrics.get('hit_at_1', 0.0)):.4f} | "
                    f"{float(metrics.get('ndcg_at_k', 0.0)):.4f} |"
                )
        comparison = retrieval_quality.get("comparison_vs_baseline", [])
        if comparison:
            lines.extend(
                [
                    "",
                    "| Candidate | Recall@K Δ | MRR Δ | Hit@1 Δ | nDCG@K Δ |",
                    "| --- | ---: | ---: | ---: | ---: |",
                ]
            )
            for row in comparison:
                lines.append(
                    "| "
                    f"{row.get('candidate', 'unknown')} | "
                    f"{float(row.get('recall_at_k_delta', 0.0)):+.4f} | "
                    f"{float(row.get('mrr_delta', 0.0)):+.4f} | "
                    f"{float(row.get('hit_at_1_delta', 0.0)):+.4f} | "
                    f"{float(row.get('ndcg_at_k_delta', 0.0)):+.4f} |"
                )

    langsmith_sync = report.get("langsmith_sync")
    if isinstance(langsmith_sync, dict):
        lines.extend(
            [
                "",
                "## LangSmith Sync",
                "",
                f"- Enabled: {bool(langsmith_sync.get('enabled', False))}",
                f"- Project: {langsmith_sync.get('project_name', 'unknown')}",
            ]
        )
        if langsmith_sync.get("reason"):
            lines.append(f"- Note: {langsmith_sync.get('reason')}")
        datasets = langsmith_sync.get("datasets", [])
        if isinstance(datasets, list) and datasets:
            lines.extend(
                [
                    "",
                    "| Dataset | Status | Examples | Dataset ID | Note |",
                    "| --- | --- | ---: | --- | --- |",
                ]
            )
            for dataset in datasets:
                if not isinstance(dataset, dict):
                    continue
                lines.append(
                    "| "
                    f"{dataset.get('name', 'unknown')} | "
                    f"{dataset.get('status', 'unknown')} | "
                    f"{int(dataset.get('example_count', 0))} | "
                    f"{dataset.get('dataset_id', '') or 'n/a'} | "
                    f"{dataset.get('note', '') or ' '} |"
                )

    lines.append("")
    return "\n".join(lines)


def _graph_retrieval_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for profile in report.get("profiles", []):
        breakdown = profile.get("category_breakdown", {})
        graph_stats = breakdown.get("graph_retrieval")
        if not graph_stats:
            continue
        task_count = int(graph_stats.get("count", 0))
        success_rate = float(graph_stats.get("success_rate", 0.0))
        profile_id = str(profile.get("profile_id", "unknown"))
        if "graph_retrieval" in profile.get("disabled_capabilities", []):
            interpretation = "Baseline-style retrieval without graph expansion."
        else:
            interpretation = "Graph-assisted retrieval enabled for multi-hop evidence."
        rows.append(
            {
                "profile_id": profile_id,
                "task_count": task_count,
                "success_rate": success_rate,
                "interpretation": interpretation,
            }
        )
    return rows


def write_markdown_report(report: dict[str, Any], output_path: str | Path) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_markdown_report(report), encoding="utf-8")
    return target


def generate_eval_report(
    *,
    dataset_path: str | Path = DEFAULT_DATASET_PATH,
    profiles_path: str | Path = DEFAULT_PROFILES_PATH,
    profile_ids: list[str] | None = None,
    report_path: str | Path = DEFAULT_REPORT_PATH,
    sync_langsmith: bool = False,
) -> dict[str, Any]:
    tasks = load_dataset(dataset_path)
    profiles = select_profiles(load_profiles(profiles_path), profile_ids)
    retrieval_cases = (
        load_retrieval_eval_dataset()
        if DEFAULT_RETRIEVAL_EVAL_PATH.exists()
        else None
    )
    report = run_profiles(tasks, profiles, retrieval_cases=retrieval_cases)
    if sync_langsmith:
        from backend.evals.langsmith_sync import sync_local_datasets

        report["langsmith_sync"] = sync_local_datasets(
            tasks_path=dataset_path,
            retrieval_path=DEFAULT_RETRIEVAL_EVAL_PATH,
        )

    output = write_report(report, report_path)
    markdown_output = write_markdown_report(report, Path(report_path).with_suffix(".md"))
    return {
        "report": report,
        "output": output,
        "markdown_output": markdown_output,
        "dataset_size": len(tasks),
        "profiles": [profile.id for profile in profiles],
        "langsmith_sync": report.get("langsmith_sync"),
    }


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
    parser.add_argument(
        "--langsmith-sync",
        action="store_true",
        help="Sync local eval datasets to LangSmith when configured.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    result = generate_eval_report(
        dataset_path=args.dataset,
        profiles_path=args.profiles,
        profile_ids=args.profile_ids,
        report_path=args.output,
        sync_langsmith=args.langsmith_sync,
    )
    print(
        json.dumps(
            {
                "output": str(result["output"]),
                "markdown_output": str(result["markdown_output"]),
                "dataset_size": result["dataset_size"],
                "profiles": result["profiles"],
                "langsmith_sync": result["langsmith_sync"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
