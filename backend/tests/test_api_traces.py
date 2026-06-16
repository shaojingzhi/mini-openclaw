"""Integration tests for the /api/traces endpoints."""

from __future__ import annotations

import importlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

app_mod = importlib.import_module("backend.app")
tr_mod = importlib.import_module("backend.traces_store")


class ApiTracesTests(unittest.TestCase):
    def test_list_traces_returns_recent_summaries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            traces_dir = Path(tmp)
            with patch.object(tr_mod, "TRACES_DIR", traces_dir):
                first = tr_mod.create_trace(session_id="alpha", model_name="gpt-5.4")
                first["trace_id"] = "trace_a"
                first["start_time"] = "2026-06-17T00:00:00+00:00"
                tr_mod.finalize_trace(first, final_status="success")
                tr_mod.save_trace(first)

                second = tr_mod.create_trace(session_id="beta", model_name="gpt-5.4")
                second["trace_id"] = "trace_b"
                second["start_time"] = "2026-06-17T00:01:00+00:00"
                tr_mod.finalize_trace(second, final_status="error")
                tr_mod.save_trace(second)

                client = TestClient(app_mod.app)
                response = client.get("/api/traces")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual([item["trace_id"] for item in body["traces"]], ["trace_b", "trace_a"])
        self.assertEqual(body["traces"][0]["final_status"], "error")
        self.assertEqual(body["traces"][1]["final_status"], "success")

    def test_get_trace_returns_full_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            traces_dir = Path(tmp)
            with patch.object(tr_mod, "TRACES_DIR", traces_dir):
                trace = tr_mod.create_trace(session_id="alpha", model_name="gpt-5.4")
                trace["trace_id"] = "trace_a"
                tr_mod.append_event(trace, kind="tool_call", payload={"name": "read_file"})
                tr_mod.finalize_trace(trace, final_status="success")
                tr_mod.save_trace(trace)
                client = TestClient(app_mod.app)
                response = client.get("/api/traces/trace_a")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["trace_id"], "trace_a")
        self.assertEqual(response.json()["session_id"], "alpha")
        self.assertEqual(response.json()["final_status"], "success")
        self.assertEqual(len(response.json()["events"]), 1)

    def test_get_trace_missing_returns_404(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            traces_dir = Path(tmp)
            with patch.object(tr_mod, "TRACES_DIR", traces_dir):
                client = TestClient(app_mod.app)
                response = client.get("/api/traces/missing")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "trace not found")


if __name__ == "__main__":
    unittest.main()
