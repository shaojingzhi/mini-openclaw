"""Unit tests for backend.evals.runner."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.evals.runner import (
    EvaluationTask,
    RunResult,
    aggregate_report,
    load_dataset,
    run_dataset,
    write_report,
)


class LoadDatasetTests(unittest.TestCase):
    def test_load_dataset_reads_seed_tasks(self) -> None:
        tasks = load_dataset()
        self.assertGreaterEqual(len(tasks), 20)
        self.assertEqual(tasks[0].id, "eval-001")
        self.assertIn(tasks[0].category, {"file_reading", "skills", "terminal", "knowledge_retrieval", "multi_turn_context"})

    def test_load_dataset_rejects_non_array(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text('{"oops": true}', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_dataset(path)


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


class RunAndWriteTests(unittest.TestCase):
    def test_run_dataset_and_write_report(self) -> None:
        tasks = [
            EvaluationTask("task-1", "skills", "prompt", "expected", ["skills"], ["read_file"])
        ]

        def evaluator(task: EvaluationTask) -> RunResult:
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

        report = run_dataset(tasks, evaluator=evaluator)
        self.assertEqual(report["dataset_size"], 1)
        self.assertEqual(report["task_success_rate"], 1.0)
        self.assertEqual(report["results"][0]["notes"], "ok")

        with tempfile.TemporaryDirectory() as tmp:
            output = write_report(report, Path(tmp) / "reports" / "latest.json")
            self.assertTrue(output.exists())
            saved = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(saved["task_success_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
