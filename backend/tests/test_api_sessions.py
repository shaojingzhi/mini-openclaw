"""Integration tests for the /api/sessions endpoint."""

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


class ApiSessionsTests(unittest.TestCase):
    def test_list_sessions_returns_seeded_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sessions_dir = Path(tmp)
            (sessions_dir / "alpha.json").write_text(
                json.dumps(
                    [
                        {"role": "user", "content": "hi"},
                        {"role": "assistant", "content": "hello"},
                    ]
                ),
                encoding="utf-8",
            )
            (sessions_dir / "beta.json").write_text(
                json.dumps(
                    [
                        {"role": "user", "content": "ping"},
                    ]
                ),
                encoding="utf-8",
            )

            with patch.object(ss_mod, "SESSIONS_DIR", sessions_dir):
                client = TestClient(app_mod.app)
                response = client.get("/api/sessions")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        by_name = {item["name"]: item for item in body["sessions"]}
        self.assertEqual(set(by_name), {"alpha", "beta"})
        self.assertEqual(by_name["alpha"]["message_count"], 2)
        self.assertEqual(by_name["beta"]["message_count"], 1)
        self.assertEqual(by_name["alpha"]["preview"], "hi")
        self.assertTrue(by_name["alpha"]["last_modified"])
        self.assertTrue(by_name["beta"]["last_modified"])

    def test_list_sessions_returns_empty_for_missing_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sessions_dir = Path(tmp) / "missing"
            with patch.object(ss_mod, "SESSIONS_DIR", sessions_dir):
                client = TestClient(app_mod.app)
                response = client.get("/api/sessions")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"sessions": []})

    def test_get_session_keeps_legacy_handoff_without_inventing_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sessions_dir = Path(tmp)
            (sessions_dir / "legacy.json").write_text(
                json.dumps(
                    [
                        {"role": "user", "content": "Please review this."},
                        {
                            "role": "assistant",
                            "content": "Here is the review.",
                            "handoff_id": "handoff_legacy",
                            "handoff_from_agent_id": "lighthouse",
                            "handoff_reason": "A stricter review was requested.",
                        },
                    ]
                ),
                encoding="utf-8",
            )

            with patch.object(ss_mod, "SESSIONS_DIR", sessions_dir):
                client = TestClient(app_mod.app)
                response = client.get("/api/sessions/legacy")

        self.assertEqual(response.status_code, 200)
        message = response.json()["messages"][-1]
        self.assertEqual(message["handoff_id"], "handoff_legacy")
        self.assertNotIn("handoff_task", message)
        self.assertNotIn("handoff_evidence_count", message)


if __name__ == "__main__":
    unittest.main()
