"""Integration tests for the /api/chat endpoint."""

from __future__ import annotations

import importlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

app_mod = importlib.import_module("backend.app")
ss_mod = importlib.import_module("backend.sessions_store")


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
            with patch.object(ss_mod, "SESSIONS_DIR", Path(tmp)), patch.object(
                app_mod, "build_agent", return_value=agent
            ):
                client = TestClient(app_mod.app)
                response = client.post(
                    "/api/chat",
                    json={"message": "say hello", "session_id": "main", "stream": True},
                )
                persisted = json.loads((Path(tmp) / "main.json").read_text(encoding="utf-8"))

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

    def test_non_streaming_chat_returns_json_and_persists_messages(self) -> None:
        agent = _InvokeAgent()
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(ss_mod, "SESSIONS_DIR", Path(tmp)), patch.object(
                app_mod, "build_agent", return_value=agent
            ):
                client = TestClient(app_mod.app)
                response = client.post(
                    "/api/chat",
                    json={"message": "say hello", "session_id": "main", "stream": False},
                )
                persisted = json.loads((Path(tmp) / "main.json").read_text(encoding="utf-8"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"reply": "plain reply"})
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


if __name__ == "__main__":
    unittest.main()
