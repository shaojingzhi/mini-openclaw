"""Unit tests for backend.evals.runner."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.evals.runner import (
    EvalProfile,
    EvaluationTask,
    RetrievalEvalCase,
    RunResult,
    aggregate_report,
    compute_retrieval_metrics,
    load_dataset,
    load_profiles,
    load_retrieval_eval_dataset,
    render_markdown_report,
    run_retrieval_evaluation,
    run_dataset,
    run_profiles,
    select_profiles,
    write_markdown_report,
    write_report,
)


class LoadDatasetTests(unittest.TestCase):
    def test_load_dataset_reads_seed_tasks(self) -> None:
        tasks = load_dataset()
        self.assertGreaterEqual(len(tasks), 20)
        self.assertEqual(tasks[0].id, "eval-001")
        self.assertIn(tasks[0].category, {"file_reading", "skills", "terminal", "knowledge_retrieval", "multi_turn_context", "graph_retrieval"})

    def test_load_dataset_includes_graph_retrieval_tasks(self) -> None:
        tasks = load_dataset()
        graph_tasks = [task for task in tasks if task.category == "graph_retrieval"]

        self.assertGreaterEqual(len(graph_tasks), 5)
        for task in graph_tasks:
            self.assertIn("graph_retrieval", task.tags)
            self.assertIn("multi_hop", task.tags)
            self.assertIn("search_knowledge_base", task.required_tools)

    def test_load_dataset_rejects_non_array(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text('{"oops": true}', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_dataset(path)


class LoadRetrievalEvalDatasetTests(unittest.TestCase):
    def test_load_retrieval_eval_dataset_reads_labeled_cases(self) -> None:
        cases = load_retrieval_eval_dataset()

        self.assertGreaterEqual(len(cases), 5)
        self.assertEqual(cases[0].id, "rq-001")
        self.assertIn("baseline", cases[0].strategies)
        self.assertIn("graph_assisted", cases[0].strategies)
        self.assertGreaterEqual(len(cases[0].relevant_ids), 2)

    def test_load_retrieval_eval_dataset_rejects_non_array(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text('{"oops": true}', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_retrieval_eval_dataset(path)


class LoadProfilesTests(unittest.TestCase):
    def test_load_profiles_reads_defaults(self) -> None:
        profiles = load_profiles()
        self.assertEqual(
            [profile.id for profile in profiles],
            ["baseline", "no_memory", "no_skills", "no_retrieval", "no_graph_retrieval"],
        )

    def test_select_profiles_filters_requested_ids(self) -> None:
        profiles = load_profiles()
        selected = select_profiles(profiles, ["baseline", "no_retrieval"])
        self.assertEqual([profile.id for profile in selected], ["baseline", "no_retrieval"])

    def test_select_profiles_rejects_unknown_id(self) -> None:
        with self.assertRaises(ValueError):
            select_profiles(load_profiles(), ["missing-profile"])


class AggregateReportTests(unittest.TestCase):
    def test_aggregate_report_computes_expected_metrics(self) -> None:
        tasks = [
            EvaluationTask("a", "file_reading", "p", "e", [], ["read_file"]),
            EvaluationTask("b", "terminal", "p", "e", [], ["terminal"]),
        ]
        results = [
            RunResult("a", "file_reading", True, 100.0, 1, 1, 0, None),
            RunResult("b", "terminal", False, 300.0, 2, 1, 1, "tool_timeout"),
        ]

        report = aggregate_report(tasks, results)

        self.assertEqual(report["task_success_rate"], 0.5)
        self.assertEqual(report["tool_call_success_rate"], 0.6667)
        self.assertEqual(report["average_latency_ms"], 200.0)
        self.assertEqual(report["average_tool_calls"], 1.5)
        self.assertEqual(report["failure_category_distribution"], {"tool_timeout": 1})
        self.assertEqual(report["category_breakdown"]["file_reading"]["success_rate"], 1.0)
        self.assertEqual(report["category_breakdown"]["terminal"]["success_rate"], 0.0)

    def test_aggregate_report_handles_empty_inputs(self) -> None:
        report = aggregate_report([], [])
        self.assertEqual(report["task_success_rate"], 0.0)
        self.assertEqual(report["failure_category_distribution"], {})


class RetrievalMetricsTests(unittest.TestCase):
    def test_compute_retrieval_metrics_scores_ranked_results(self) -> None:
        metrics = compute_retrieval_metrics(
            ["miss", "rel-b", "rel-a", "other"],
            ["rel-a", "rel-b", "rel-c"],
            top_k=3,
        )

        self.assertEqual(metrics["recall_at_k"], 0.6667)
        self.assertEqual(metrics["mrr"], 0.5)
        self.assertEqual(metrics["hit_at_1"], 0.0)
        self.assertEqual(metrics["ndcg_at_k"], 0.5307)

    def test_compute_retrieval_metrics_rejects_invalid_k(self) -> None:
        with self.assertRaises(ValueError):
            compute_retrieval_metrics(["a"], ["a"], top_k=0)

    def test_run_retrieval_evaluation_compares_strategies(self) -> None:
        cases = [
            RetrievalEvalCase(
                id="case-1",
                query="q1",
                relevant_ids=["a", "b"],
                strategies={
                    "baseline": ["a", "x", "y"],
                    "graph_assisted": ["a", "b", "x"],
                },
            ),
            RetrievalEvalCase(
                id="case-2",
                query="q2",
                relevant_ids=["c"],
                strategies={
                    "baseline": ["x", "c"],
                    "graph_assisted": ["c", "x"],
                },
            ),
        ]

        report = run_retrieval_evaluation(cases, top_k=2)

        self.assertEqual(report["case_count"], 2)
        self.assertEqual(report["strategies"], ["baseline", "graph_assisted"])
        self.assertEqual(report["summary"]["baseline"]["recall_at_k"], 0.75)
        self.assertEqual(report["summary"]["graph_assisted"]["recall_at_k"], 1.0)
        self.assertEqual(
            report["comparison_vs_baseline"][0]["recall_at_k_delta"],
            0.25,
        )
        self.assertEqual(len(report["cases"]), 4)


class RunAndWriteTests(unittest.TestCase):
    def test_run_dataset_and_write_report(self) -> None:
        tasks = [
            EvaluationTask("task-1", "skills", "prompt", "expected", ["skills"], ["read_file"])
        ]
        profile = EvalProfile("baseline", "Full capability baseline.", [])

        def evaluator(task: EvaluationTask, active_profile: EvalProfile) -> RunResult:
            self.assertEqual(active_profile.id, "baseline")
            return RunResult(
                task_id=task.id,
                category=task.category,
                success=True,
                latency_ms=42.0,
                tool_calls=1,
                tool_successes=1,
                tool_failures=0,
                failure_category=None,
                notes="ok",
            )

        report = run_dataset(tasks, profile=profile, evaluator=evaluator)
        self.assertEqual(report["dataset_size"], 1)
        self.assertEqual(report["task_success_rate"], 1.0)
        self.assertEqual(report["profile_id"], "baseline")
        self.assertEqual(report["results"][0]["notes"], "ok")

        with tempfile.TemporaryDirectory() as tmp:
            output = write_report(report, Path(tmp) / "reports" / "latest.json")
            self.assertTrue(output.exists())
            saved = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(saved["task_success_rate"], 1.0)

    def test_run_profiles_builds_ablation_comparison(self) -> None:
        tasks = [
            EvaluationTask("memory-task", "multi_turn_context", "p", "e", ["memory"], []),
            EvaluationTask("skill-task", "skills", "p", "e", ["skills"], ["read_file"]),
            EvaluationTask("retrieval-task", "knowledge_retrieval", "p", "e", ["knowledge"], ["search_knowledge_base"]),
        ]
        profiles = [
            EvalProfile("baseline", "Full capability baseline.", []),
            EvalProfile("no_memory", "Disable memory.", ["memory"]),
            EvalProfile("no_skills", "Disable skills.", ["skills"]),
        ]

        report = run_profiles(tasks, profiles)

        self.assertEqual(report["profile_ids"], ["baseline", "no_memory", "no_skills"])
        self.assertEqual(len(report["profiles"]), 3)
        self.assertEqual(len(report["ablation_comparison"]), 2)
        self.assertEqual(report["profiles"][0]["task_success_rate"], 1.0)
        self.assertLess(report["profiles"][1]["task_success_rate"], 1.0)

    def test_render_markdown_report_includes_ablation_table(self) -> None:
        tasks = [
            EvaluationTask("skill-task", "skills", "p", "e", ["skills"], ["read_file"])
        ]
        profiles = [
            EvalProfile("baseline", "Full capability baseline.", []),
            EvalProfile("no_skills", "Disable skills.", ["skills"]),
        ]

        report = run_profiles(tasks, profiles)
        markdown = render_markdown_report(report)

        self.assertIn("# Mini-OpenClaw Evaluation Report", markdown)
        self.assertIn("## Profile Summary", markdown)
        self.assertIn("## Ablation Comparison vs Baseline", markdown)
        self.assertIn("| Candidate | Task Success Δ |", markdown)

        with tempfile.TemporaryDirectory() as tmp:
            output = write_markdown_report(report, Path(tmp) / "reports" / "latest.md")
            self.assertTrue(output.exists())
            self.assertIn("no_skills", output.read_text(encoding="utf-8"))

    def test_render_markdown_report_includes_graph_retrieval_section(self) -> None:
        tasks = [
            EvaluationTask(
                "graph-task",
                "graph_retrieval",
                "p",
                "e",
                ["graph_retrieval", "multi_hop"],
                ["search_knowledge_base"],
            )
        ]
        profiles = [
            EvalProfile("baseline", "Full capability baseline.", []),
            EvalProfile(
                "no_graph_retrieval",
                "Disable graph expansion.",
                ["graph_retrieval"],
            ),
        ]

        report = run_profiles(tasks, profiles)
        markdown = render_markdown_report(report)

        self.assertIn("## Graph-Assisted Retrieval Check", markdown)
        self.assertIn("multi-hop questions", markdown)
        self.assertIn("no_graph_retrieval", markdown)
        self.assertIn("Baseline-style retrieval without graph expansion.", markdown)
        self.assertLess(report["profiles"][1]["task_success_rate"], 1.0)

    def test_render_markdown_report_includes_retrieval_quality_metrics(self) -> None:
        tasks = [
            EvaluationTask("retrieval-task", "knowledge_retrieval", "p", "e", ["knowledge"], ["search_knowledge_base"])
        ]
        profiles = [EvalProfile("baseline", "Full capability baseline.", [])]
        retrieval_cases = [
            RetrievalEvalCase(
                id="case-1",
                query="q1",
                relevant_ids=["a", "b"],
                strategies={
                    "baseline": ["a", "x"],
                    "graph_assisted": ["a", "b"],
                },
            )
        ]

        report = run_profiles(
            tasks,
            profiles,
            retrieval_cases=retrieval_cases,
            retrieval_top_k=2,
        )
        markdown = render_markdown_report(report)

        self.assertIn("## Retrieval Quality Metrics", markdown)
        self.assertIn("| Strategy | Cases | Recall@K | MRR | Hit@1 | nDCG@K |", markdown)
        self.assertIn("graph_assisted", markdown)
        self.assertIn("Recall@K Δ", markdown)

    def test_render_markdown_report_includes_langsmith_sync_section(self) -> None:
        tasks = [EvaluationTask("task-1", "skills", "p", "e", [], [])]
        profiles = [EvalProfile("baseline", "Full capability baseline.", [])]
        report = run_profiles(tasks, profiles)
        report["langsmith_sync"] = {
            "enabled": True,
            "project_name": "mini-openclaw-evals",
            "reason": "",
            "datasets": [
                {
                    "name": "mini-openclaw-core-tasks",
                    "status": "created",
                    "example_count": 1,
                    "dataset_id": "dataset-id",
                    "note": "",
                }
            ],
        }

        markdown = render_markdown_report(report)

        self.assertIn("## LangSmith Sync", markdown)
        self.assertIn("mini-openclaw-core-tasks", markdown)
        self.assertIn("dataset-id", markdown)


if __name__ == "__main__":
    unittest.main()
