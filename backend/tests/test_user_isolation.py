"""Integration tests for minimal user isolation."""

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
tr_mod = importlib.import_module("backend.traces_store")
us_mod = importlib.import_module("backend.user_state")


class _InvokeAgent:
    async def ainvoke(self, payload):
        return {"messages": [{"role": "assistant", "content": "isolated reply"}]}


class UserIsolationTests(unittest.TestCase):
    def test_chat_sessions_are_isolated_by_user_header(self) -> None:
        agent = _InvokeAgent()
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            data_users_dir = project_root / "backend" / "data" / "users"
            traces_dir = project_root / "backend" / "data" / "traces"
            with patch.object(us_mod, "DATA_USERS_DIR", data_users_dir), patch.object(tr_mod, "TRACES_DIR", traces_dir), patch.object(
                app_mod, "build_agent", return_value=agent
            ), patch.object(ss_mod, "SESSIONS_DIR", project_root / "backend" / "sessions"):
                client = TestClient(app_mod.app)
                response_a = client.post(
                    "/api/chat",
                    headers={"X-User-ID": "alice"},
                    json={"message": "hello from alice", "session_id": "main", "stream": False},
                )
                response_b = client.post(
                    "/api/chat",
                    headers={"X-User-ID": "bob"},
                    json={"message": "hello from bob", "session_id": "main", "stream": False},
                )
                alice_session = (data_users_dir / "alice" / "sessions" / "main.json").read_text(encoding="utf-8")
                bob_session = (data_users_dir / "bob" / "sessions" / "main.json").read_text(encoding="utf-8")

        self.assertEqual(response_a.status_code, 200)
        self.assertEqual(response_b.status_code, 200)
        self.assertIn("hello from alice", alice_session)
        self.assertNotIn("hello from bob", alice_session)
        self.assertIn("hello from bob", bob_session)
        self.assertNotIn("hello from alice", bob_session)

    def test_file_access_respects_user_workspace_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            data_users_dir = project_root / "backend" / "data" / "users"
            (data_users_dir / "alice" / "workspace").mkdir(parents=True, exist_ok=True)
            (data_users_dir / "bob" / "workspace").mkdir(parents=True, exist_ok=True)
            (project_root / "backend" / "skills").mkdir(parents=True, exist_ok=True)
            (data_users_dir / "alice" / "workspace" / "USER.md").write_text("alice workspace", encoding="utf-8")
            (data_users_dir / "bob" / "workspace" / "USER.md").write_text("bob workspace", encoding="utf-8")

            with patch.object(app_mod, "PROJECT_ROOT", project_root), patch.object(us_mod, "DATA_USERS_DIR", data_users_dir):
                client = TestClient(app_mod.app)
                alice_response = client.get(
                    "/api/files",
                    headers={"X-User-ID": "alice"},
                    params={"path": "backend/data/users/alice/workspace/USER.md"},
                )
                bob_response = client.get(
                    "/api/files",
                    headers={"X-User-ID": "bob"},
                    params={"path": "backend/data/users/bob/workspace/USER.md"},
                )

        self.assertEqual(alice_response.status_code, 200)
        self.assertEqual(bob_response.status_code, 200)
        self.assertEqual(alice_response.json()["content"], "alice workspace")
        self.assertEqual(bob_response.json()["content"], "bob workspace")


if __name__ == "__main__":
    unittest.main()
