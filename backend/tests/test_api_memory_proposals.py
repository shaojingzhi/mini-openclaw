"""Integration tests for memory proposal review endpoints."""

from __future__ import annotations

import importlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

app_mod = importlib.import_module("backend.app")
ps_mod = importlib.import_module("backend.memory.proposals_store")
us_mod = importlib.import_module("backend.user_state")


class ApiMemoryProposalTests(unittest.TestCase):
    def _proposal(self, *, user_id: str, content: str) -> dict[str, object]:
        proposal, _ = ps_mod.create_proposal(
            user_id=user_id,
            session_id="main",
            target="user_capsule",
            memory_type="user_preference",
            content=content,
            rationale="Explicitly confirmed by the user.",
        )
        return proposal

    def test_lists_filters_and_approves_current_users_proposal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(ps_mod, "MEMORY_DIR", root / "memory"), patch.object(
                us_mod, "DATA_USERS_DIR", root / "users"
            ):
                alice = self._proposal(user_id="alice", content="Alice preference")
                self._proposal(user_id="bob", content="Bob preference")
                client = TestClient(app_mod.app)

                listed = client.get("/api/memory/proposals", headers={"X-User-ID": "alice"})
                approved = client.post(
                    f"/api/memory/proposals/{alice['proposal_id']}/approve",
                    headers={"X-User-ID": "alice"},
                    json={"reason": "Approved for future conversations."},
                )
                filtered = client.get(
                    "/api/memory/proposals?status=approved", headers={"X-User-ID": "alice"}
                )

        self.assertEqual(listed.status_code, 200)
        self.assertEqual([item["content"] for item in listed.json()["proposals"]], ["Alice preference"])
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.json()["proposal"]["status"], "approved")
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual([item["proposal_id"] for item in filtered.json()["proposals"]], [alice["proposal_id"]])

    def test_rejects_invalid_review_requests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(ps_mod, "MEMORY_DIR", root / "memory"):
                proposal = self._proposal(user_id="anonymous", content="One proposal")
                client = TestClient(app_mod.app)
                missing = client.post("/api/memory/proposals/memprop_missing/approve", json={})
                rejected = client.post(
                    f"/api/memory/proposals/{proposal['proposal_id']}/reject", json={}
                )
                repeated = client.post(
                    f"/api/memory/proposals/{proposal['proposal_id']}/approve", json={}
                )
                invalid_filter = client.get("/api/memory/proposals?status=invalid")

        self.assertEqual(missing.status_code, 404)
        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(rejected.json()["proposal"]["status"], "rejected")
        self.assertEqual(repeated.status_code, 409)
        self.assertEqual(invalid_filter.status_code, 422)


if __name__ == "__main__":
    unittest.main()
