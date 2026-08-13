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
graph_mod = importlib.import_module("backend.graph.index")


class ApiTracesTests(unittest.TestCase):
    def test_list_traces_returns_recent_summaries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            traces_dir = Path(tmp)
            with patch.object(tr_mod, "TRACES_DIR", traces_dir):
                first = tr_mod.create_trace(session_id="alpha", model_name="gpt-5.4")
                first["trace_id"] = "trace_a"
                tr_mod.finalize_trace(first, final_status="success")
                tr_mod.save_trace(first)

                second = tr_mod.create_trace(
                    session_id="beta",
                    model_name="gpt-5.4",
                    selected_agent_id="spark",
                    route_reason="explicit_mention",
                )
                second["trace_id"] = "trace_b"
                tr_mod.finalize_trace(second, final_status="error")
                tr_mod.save_trace(second)

                client = TestClient(app_mod.app)
                response = client.get("/api/traces")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual([item["trace_id"] for item in body["traces"]], ["trace_b", "trace_a"])
        self.assertEqual(body["traces"][0]["final_status"], "error")
        self.assertIsNone(body["traces"][0]["error_category"])
        self.assertEqual(body["traces"][0]["active_agent_id"], "spark")
        self.assertEqual(body["traces"][0]["route_reason"], "explicit_mention")
        self.assertEqual(body["traces"][0]["handoff_count"], 0)
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

    def test_graph_summary_returns_counts(self) -> None:
        graph = {
            "schema_version": 1,
            "sources": {"knowledge": "backend/knowledge"},
            "nodes": [
                {"id": "document:a", "type": "document", "label": "a", "metadata": {}},
                {"id": "tool:b", "type": "tool", "label": "b", "metadata": {}},
            ],
            "edges": [
                {
                    "id": "edge:1",
                    "source": "document:a",
                    "target": "tool:b",
                    "type": "uses_tool",
                    "metadata": {},
                }
            ],
        }
        with patch.object(graph_mod, "load_graph", return_value=graph):
            client = TestClient(app_mod.app)
            response = client.get("/api/graph")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["available"])
        self.assertEqual(body["summary"]["node_count"], 2)
        self.assertEqual(body["summary"]["edge_counts"]["uses_tool"], 1)

    def test_graph_node_detail_returns_connected_edges(self) -> None:
        graph = {
            "schema_version": 1,
            "sources": {},
            "nodes": [
                {"id": "document:a", "type": "document", "label": "a", "metadata": {}},
                {"id": "tool:b", "type": "tool", "label": "b", "metadata": {}},
            ],
            "edges": [
                {
                    "id": "edge:1",
                    "source": "document:a",
                    "target": "tool:b",
                    "type": "uses_tool",
                    "metadata": {},
                }
            ],
        }
        with patch.object(graph_mod, "load_graph", return_value=graph):
            client = TestClient(app_mod.app)
            response = client.get("/api/graph/nodes/document%3Aa")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["node"]["id"], "document:a")
        self.assertEqual(len(body["edges"]), 1)

    def test_graph_node_missing_returns_404(self) -> None:
        with patch.object(graph_mod, "load_graph", return_value={"nodes": [], "edges": []}):
            client = TestClient(app_mod.app)
            response = client.get("/api/graph/nodes/missing")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "graph node not found")

    def test_graph_demo_writes_trace_with_graph_metadata(self) -> None:
        graph_result = {
            "available": True,
            "direct_node_ids": ["document:eval"],
            "expanded_node_ids": ["workspace:demo"],
            "edge_types": ["mentions"],
            "evidence": [
                {
                    "id": "document:eval",
                    "type": "document",
                    "label": "eval_agent_notes.md",
                    "path": "backend/knowledge/eval_agent_notes.md",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            traces_dir = Path(tmp) / "traces"
            sessions_dir = Path(tmp) / "sessions"
            with patch.object(tr_mod, "TRACES_DIR", traces_dir), patch.object(
                app_mod.sessions_store, "SESSIONS_DIR", sessions_dir
            ), patch.object(graph_mod, "expand_graph_evidence", return_value=graph_result):
                client = TestClient(app_mod.app)
                response = client.post(
                    "/api/graph/demo",
                    json={"session_id": "main", "message": "run graph demo"},
                )
                trace_files = list(traces_dir.glob("*.json"))
                trace = tr_mod.load_trace(trace_files[0].stem)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("Graph-assisted retrieval demo completed.", body["reply"])
        self.assertTrue(body["trace_id"].startswith("trace_"))
        self.assertIsNotNone(trace)
        self.assertEqual(trace["model_name"], "graph-demo-local")
        self.assertEqual(trace["graph_retrieval"]["evidence_count"], 1)
        self.assertEqual(trace["events"][1]["kind"], "tool_call")
        self.assertEqual(trace["events"][2]["kind"], "graph_retrieval")


if __name__ == "__main__":
    unittest.main()
