"""Integration tests for the /api/chat endpoint."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

app_mod = importlib.import_module("backend.app")
ss_mod = importlib.import_module("backend.sessions_store")
tr_mod = importlib.import_module("backend.traces_store")
us_mod = importlib.import_module("backend.user_state")
ps_mod = importlib.import_module("backend.memory.proposals_store")


class _StreamingAgent:
    def __init__(self) -> None:
        self.payloads: list[dict[str, object]] = []

    async def astream_events(self, payload, version="v2"):
        self.payloads.append(payload)
        yield {"type": "thought", "data": {"content": "thinking"}}
        yield {
            "type": "tool_call",
            "data": {"name": "python_repl", "input": {"query": "print(2 + 2)"}},
        }
        yield {
            "type": "tool_result",
            "data": {"name": "python_repl", "content": "4"},
        }
        yield {"type": "final", "data": {"content": "hello back"}}


class _GraphStreamingAgent:
    async def astream_events(self, payload, version="v2"):
        yield {"type": "thought", "data": {"content": "graph thinking"}}
        yield {
            "type": "tool_call",
            "data": {
                "name": "search_knowledge_base",
                "input": {
                    "query": "connect eval notes to interview demo",
                    "use_graph": True,
                },
            },
        }
        yield {
            "type": "tool_result",
            "data": {
                "name": "search_knowledge_base",
                "content": "Direct matches:\n...\n\nGraph-expanded evidence:\n...",
            },
        }
        yield {"type": "final", "data": {"content": "graph answer"}}


class _InvokeAgent:
    def __init__(self) -> None:
        self.payloads: list[dict[str, object]] = []

    async def ainvoke(self, payload):
        self.payloads.append(payload)
        return {"messages": [{"role": "assistant", "content": "plain reply"}]}


class _FlakyRecoverableAgent:
    def __init__(self) -> None:
        self.calls = 0

    async def ainvoke(self, payload):
        self.calls += 1
        if self.calls == 1:
            raise TimeoutError("tool timed out while fetching data")
        return {"messages": [{"role": "assistant", "content": "recovered reply"}]}


class ApiChatTests(unittest.TestCase):
    def test_streaming_chat_emits_sse_events_and_persists_messages(self) -> None:
        agent = _StreamingAgent()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            traces_dir = tmp_path / "traces"
            data_users_dir = tmp_path / "users"
            with patch.object(ss_mod, "SESSIONS_DIR", tmp_path), patch.object(us_mod, "DATA_USERS_DIR", data_users_dir), patch.object(tr_mod, "TRACES_DIR", traces_dir), patch.object(
                app_mod, "build_agent", return_value=agent
            ):
                client = TestClient(app_mod.app)
                response = client.post(
                    "/api/chat",
                    json={"message": "say hello", "session_id": "main", "stream": True},
                )
                persisted = ss_mod.load_session("main", user_id="anonymous")
                trace_files = list(traces_dir.glob("*.json"))
                trace = json.loads(trace_files[0].read_text(encoding="utf-8"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "text/event-stream; charset=utf-8")
        body = response.text
        self.assertIn("event: thought", body)
        self.assertIn('data: {"content": "thinking"}', body)
        self.assertIn("event: tool_call", body)
        self.assertIn("event: tool_result", body)
        self.assertIn("event: final", body)
        self.assertIn('data: {"content": "hello back"}', body)
        self.assertEqual(
            agent.payloads,
            [{"messages": [{"role": "user", "content": "say hello"}]}],
        )
        self.assertEqual(
            persisted,
            [
                {"role": "user", "content": "say hello"},
                {"role": "assistant", "content": "hello back"},
            ],
        )
        self.assertEqual(trace["session_id"], "main")
        self.assertEqual(trace["final_status"], "success")
        self.assertEqual(trace["model_name"], os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
        self.assertEqual(len(trace["tool_calls"]), 1)
        self.assertEqual(len(trace["events"]), 6)
        self.assertEqual(trace["events"][1]["kind"], "memory_loaded")
        self.assertEqual(trace["events"][1]["payload"]["memory_count"], 0)

    def test_streaming_graph_search_records_trace_metadata(self) -> None:
        agent = _GraphStreamingAgent()
        graph_result = {
            "available": True,
            "direct_node_ids": ["document:eval"],
            "expanded_node_ids": ["workspace:demo", "trace:last"],
            "edge_types": ["mentions", "contains"],
            "evidence": [{"id": "document:eval"}, {"id": "workspace:demo"}],
        }
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            traces_dir = tmp_path / "traces"
            data_users_dir = tmp_path / "users"
            with patch.object(ss_mod, "SESSIONS_DIR", tmp_path), patch.object(us_mod, "DATA_USERS_DIR", data_users_dir), patch.object(tr_mod, "TRACES_DIR", traces_dir), patch.object(
                app_mod, "build_agent", return_value=agent
            ), patch.object(app_mod.graph_index, "expand_graph_evidence", return_value=graph_result) as expand_graph:
                client = TestClient(app_mod.app)
                response = client.post(
                    "/api/chat",
                    json={"message": "run graph demo", "session_id": "main", "stream": True},
                )
                trace_files = list(traces_dir.glob("*.json"))
                trace = json.loads(trace_files[0].read_text(encoding="utf-8"))

        self.assertEqual(response.status_code, 200)
        expand_graph.assert_called_once_with("connect eval notes to interview demo")
        self.assertEqual(
            trace["graph_retrieval"],
            {
                "direct_node_ids": ["document:eval"],
                "expanded_node_ids": ["workspace:demo", "trace:last"],
                "edge_types": ["mentions", "contains"],
                "evidence_count": 2,
            },
        )
        self.assertEqual(trace["events"][-2]["kind"], "graph_retrieval")
        self.assertIn("Graph-expanded evidence", response.text)

    def test_non_streaming_chat_returns_json_and_persists_messages(self) -> None:
        agent = _InvokeAgent()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            traces_dir = tmp_path / "traces"
            data_users_dir = tmp_path / "users"
            with patch.object(ss_mod, "SESSIONS_DIR", tmp_path), patch.object(us_mod, "DATA_USERS_DIR", data_users_dir), patch.object(tr_mod, "TRACES_DIR", traces_dir), patch.object(
                app_mod, "build_agent", return_value=agent
            ):
                client = TestClient(app_mod.app)
                response = client.post(
                    "/api/chat",
                    json={"message": "say hello", "session_id": "main", "stream": False},
                )
                persisted = ss_mod.load_session("main", user_id="anonymous")
                trace_files = list(traces_dir.glob("*.json"))
                trace = json.loads(trace_files[0].read_text(encoding="utf-8"))

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["reply"], "plain reply")
        self.assertTrue(body["trace_id"].startswith("trace_"))
        self.assertEqual(
            agent.payloads,
            [{"messages": [{"role": "user", "content": "say hello"}]}],
        )
        self.assertEqual(
            persisted,
            [
                {"role": "user", "content": "say hello"},
                {"role": "assistant", "content": "plain reply"},
            ],
        )
        self.assertEqual(trace["final_status"], "success")
        self.assertEqual(trace["events"][-1]["kind"], "final")

    def test_chat_loads_approved_memory_and_records_created_proposal(self) -> None:
        agent = _InvokeAgent()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            traces_dir = tmp_path / "traces"
            data_users_dir = tmp_path / "users"
            with patch.object(ss_mod, "SESSIONS_DIR", tmp_path / "sessions"), patch.object(
                us_mod, "DATA_USERS_DIR", data_users_dir
            ), patch.object(tr_mod, "TRACES_DIR", traces_dir), patch.object(
                ps_mod, "MEMORY_DIR", tmp_path / "memory"
            ):
                approved, _ = ps_mod.create_proposal(
                    user_id="alice",
                    session_id="main",
                    target="user_capsule",
                    memory_type="user_preference",
                    content="Use Chinese for interview answers.",
                    rationale="The user explicitly asked for it.",
                )
                ps_mod.decide_proposal(
                    user_id="alice", proposal_id=approved["proposal_id"], decision="approved"
                )
                created, _ = ps_mod.create_proposal(
                    user_id="alice",
                    session_id="main",
                    target="project_memory",
                    memory_type="task_state",
                    content="Review the pending deployment checklist next.",
                    rationale="The user explicitly asked to retain the task state.",
                )
                build_args: dict[str, object] = {}

                def build_with_proposal(**kwargs):
                    build_args.update(kwargs)
                    kwargs["on_memory_proposal_created"](created)
                    return agent

                with patch.object(app_mod, "build_agent", side_effect=build_with_proposal):
                    client = TestClient(app_mod.app)
                    response = client.post(
                        "/api/chat",
                        headers={"X-User-ID": "alice"},
                        json={"message": "hello", "session_id": "main", "stream": False},
                    )
                trace = json.loads(next(traces_dir.glob("*.json")).read_text(encoding="utf-8"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [memory["proposal_id"] for memory in build_args["approved_memories"]],
            [approved["proposal_id"]],
        )
        events_by_kind = {event["kind"]: event["payload"] for event in trace["events"]}
        self.assertEqual(events_by_kind["memory_loaded"]["memory_count"], 1)
        self.assertEqual(events_by_kind["memory_loaded"]["approved_total"], 1)
        self.assertEqual(events_by_kind["memory_loaded"]["omitted_proposal_ids"], [])
        self.assertEqual(events_by_kind["memory_loaded"]["layer_counts"], {"user_capsule": 1})
        self.assertEqual(events_by_kind["memory_loaded"]["proposal_ids"], [approved["proposal_id"]])
        self.assertEqual(
            events_by_kind["memory_proposal_created"]["proposal_id"], created["proposal_id"]
        )

    def test_non_streaming_chat_failure_returns_categorized_payload(self) -> None:
        class _FailingAgent:
            async def ainvoke(self, payload):
                raise RuntimeError("provider timeout")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            traces_dir = tmp_path / "traces"
            data_users_dir = tmp_path / "users"
            with patch.object(ss_mod, "SESSIONS_DIR", tmp_path), patch.object(us_mod, "DATA_USERS_DIR", data_users_dir), patch.object(tr_mod, "TRACES_DIR", traces_dir), patch.object(
                app_mod, "build_agent", return_value=_FailingAgent()
            ):
                client = TestClient(app_mod.app)
                response = client.post(
                    "/api/chat",
                    json={"message": "say hello", "session_id": "main", "stream": False},
                )
                trace_files = list(traces_dir.glob("*.json"))
                trace = json.loads(trace_files[0].read_text(encoding="utf-8"))

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["error_category"], "tool_timeout")
        self.assertTrue(response.json()["recoverable"])
        self.assertIn("timeout", response.json()["error_message"])
        self.assertEqual(trace["final_status"], "error")
        self.assertEqual(trace["error_category"], "tool_timeout")
        self.assertEqual(trace["tool_failures"][0]["name"], "agent_error")
        self.assertEqual(trace["tool_failures"][0]["category"], "tool_timeout")

    def test_non_streaming_chat_retries_recoverable_failure_once(self) -> None:
        agent = _FlakyRecoverableAgent()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            traces_dir = tmp_path / "traces"
            data_users_dir = tmp_path / "users"
            with patch.object(ss_mod, "SESSIONS_DIR", tmp_path), patch.object(us_mod, "DATA_USERS_DIR", data_users_dir), patch.object(tr_mod, "TRACES_DIR", traces_dir), patch.object(
                app_mod, "build_agent", return_value=agent
            ):
                client = TestClient(app_mod.app)
                response = client.post(
                    "/api/chat",
                    json={"message": "say hello", "session_id": "main", "stream": False},
                )
                trace_files = list(traces_dir.glob("*.json"))
                trace = json.loads(trace_files[0].read_text(encoding="utf-8"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["reply"], "recovered reply")
        self.assertEqual(agent.calls, 2)
        self.assertEqual(trace["final_status"], "success")
        self.assertEqual(trace["retry_count"], 1)
        self.assertEqual(trace["events"][-2]["kind"], "runtime_retry")

    def test_streaming_chat_emits_friendly_final_on_failure(self) -> None:
        class _FailingStreamAgent:
            async def astream_events(self, payload, version="v2"):
                if False:
                    yield {"type": "thought", "data": {"content": "unused"}}
                raise RuntimeError("knowledge retrieval failed: vector index unavailable")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            traces_dir = tmp_path / "traces"
            data_users_dir = tmp_path / "users"
            with patch.object(ss_mod, "SESSIONS_DIR", tmp_path), patch.object(us_mod, "DATA_USERS_DIR", data_users_dir), patch.object(tr_mod, "TRACES_DIR", traces_dir), patch.object(
                app_mod, "build_agent", return_value=_FailingStreamAgent()
            ):
                client = TestClient(app_mod.app)
                response = client.post(
                    "/api/chat",
                    json={"message": "say hello", "session_id": "main", "stream": True},
                )
                trace_files = list(traces_dir.glob("*.json"))
                trace = json.loads(trace_files[0].read_text(encoding="utf-8"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("event: tool_result", response.text)
        self.assertIn("knowledge_retrieval_failure", response.text)
        self.assertIn("temporarily unavailable", response.text)
        self.assertEqual(trace["final_status"], "error")
        self.assertEqual(trace["error_category"], "knowledge_retrieval_failure")


if __name__ == "__main__":
    unittest.main()
