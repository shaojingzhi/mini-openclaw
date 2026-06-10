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
        self.assertEqual([item["name"] for item in body["sessions"]], ["alpha", "beta"])
        self.assertEqual(body["sessions"][0]["message_count"], 2)
        self.assertEqual(body["sessions"][1]["message_count"], 1)
        self.assertTrue(body["sessions"][0]["last_modified"])
        self.assertTrue(body["sessions"][1]["last_modified"])

    def test_list_sessions_returns_empty_for_missing_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sessions_dir = Path(tmp) / "missing"
            with patch.object(ss_mod, "SESSIONS_DIR", sessions_dir):
                client = TestClient(app_mod.app)
                response = client.get("/api/sessions")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"sessions": []})


if __name__ == "__main__":
    unittest.main()
