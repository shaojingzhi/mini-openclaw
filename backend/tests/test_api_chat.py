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


class _InvokeAgent:
    def __init__(self) -> None:
        self.payloads: list[dict[str, object]] = []

    async def ainvoke(self, payload):
        self.payloads.append(payload)
        return {"messages": [{"role": "assistant", "content": "plain reply"}]}


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
        self.assertEqual(len(trace["events"]), 5)

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

    def test_non_streaming_chat_failure_persists_error_trace(self) -> None:
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
        self.assertIn("agent execution failed", response.json()["detail"])
        self.assertEqual(trace["final_status"], "error")
        self.assertEqual(trace["tool_failures"][0]["name"], "agent_error")


if __name__ == "__main__":
    unittest.main()
