"""Integration tests for the /api/evals endpoints."""

from __future__ import annotations

import importlib
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

app_mod = importlib.import_module("backend.app")
jobs_mod = importlib.import_module("backend.evals.jobs")
runner_mod = importlib.import_module("backend.evals.runner")


class ApiEvalsTests(unittest.TestCase):
    def test_run_evals_queues_job_and_exposes_completed_status(self) -> None:
        result = {
            "output": Path("/tmp/latest.json"),
            "markdown_output": Path("/tmp/latest.md"),
            "dataset_size": 24,
            "profiles": ["baseline", "no_skills"],
            "langsmith_sync": {"enabled": False, "datasets": []},
        }

        with patch.object(jobs_mod, "generate_eval_report", return_value=result) as mock_generate:
            client = TestClient(app_mod.app)
            response = client.post("/api/evals/run", json={})

            self.assertEqual(response.status_code, 200)
            queued_body = response.json()
            self.assertTrue(queued_body["job_id"].startswith("eval_"))
            self.assertIn(queued_body["status"], {"queued", "running", "completed"})

            status_response = self._wait_for_job(client, queued_body["job_id"])

        self.assertEqual(status_response.status_code, 200)
        body = status_response.json()
        self.assertEqual(body["status"], "completed")
        self.assertIsNone(body["error"])
        self.assertEqual(body["result"]["output"], "/tmp/latest.json")
        self.assertEqual(body["result"]["markdown_output"], "/tmp/latest.md")
        self.assertEqual(body["result"]["dataset_size"], 24)
        self.assertEqual(body["result"]["profiles"], ["baseline", "no_skills"])
        self.assertEqual(body["result"]["langsmith_sync"], {"enabled": False, "datasets": []})

        mock_generate.assert_called_once()
        kwargs = mock_generate.call_args.kwargs
        self.assertEqual(kwargs["dataset_path"], str(runner_mod.DEFAULT_DATASET_PATH))
        self.assertEqual(kwargs["profiles_path"], str(runner_mod.DEFAULT_PROFILES_PATH))
        self.assertIsNone(kwargs["profile_ids"])
        self.assertFalse(kwargs["sync_langsmith"])

    def test_get_eval_job_missing_returns_404(self) -> None:
        client = TestClient(app_mod.app)
        response = client.get("/api/evals/jobs/missing")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "eval job not found")

    def _wait_for_job(self, client: TestClient, job_id: str):
        for _ in range(50):
            response = client.get(f"/api/evals/jobs/{job_id}")
            if response.json()["status"] in {"completed", "failed"}:
                return response
            time.sleep(0.02)
        self.fail(f"eval job {job_id} did not finish")


if __name__ == "__main__":
    unittest.main()
