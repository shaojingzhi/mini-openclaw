"""Unit tests for the governed long-term memory proposal store."""

from __future__ import annotations

import importlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ps_mod = importlib.import_module("backend.memory.proposals_store")
us_mod = importlib.import_module("backend.user_state")


class MemoryProposalStoreTests(unittest.TestCase):
    def _create(self, *, user_id: str = "anonymous", content: str = "Prefer concise replies."):
        return ps_mod.create_proposal(
            user_id=user_id,
            session_id="main",
            target="user_capsule",
            memory_type="user_preference",
            content=content,
            rationale="The user explicitly requested this preference.",
            confidence="high",
            signal_kind="user_instructed",
            scope="global",
        )

    def test_pending_proposal_dedupes_and_only_approval_becomes_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(ps_mod, "MEMORY_DIR", root / "memory"), patch.object(
                us_mod, "DATA_USERS_DIR", root / "users"
            ):
                proposal, created = self._create()
                duplicate, duplicate_created = self._create()

                self.assertTrue(created)
                self.assertFalse(duplicate_created)
                self.assertEqual(duplicate["proposal_id"], proposal["proposal_id"])
                self.assertEqual(ps_mod.list_approved_memories(user_id="anonymous"), [])

                approved = ps_mod.decide_proposal(
                    user_id="anonymous",
                    proposal_id=proposal["proposal_id"],
                    decision="approved",
                    reason="Keep this preference.",
                )

                self.assertEqual(approved["status"], "approved")
                self.assertEqual(
                    [memory["proposal_id"] for memory in ps_mod.list_approved_memories(user_id="anonymous")],
                    [proposal["proposal_id"]],
                )
                materialized = ps_mod.materialized_memory_paths("anonymous")
                user_profile = materialized["user_capsule"].read_text(encoding="utf-8")
                self.assertIn("# User Profile", user_profile)
                self.assertIn(proposal["proposal_id"], user_profile)
                self.assertIn("source_session_id: main", user_profile)
                self.assertIn("rationale: The user explicitly requested this preference.", user_profile)
                self.assertIn("No approved entries yet.", materialized["agent_behavior"].read_text())
                self.assertEqual(
                    ps_mod.proposals_path().read_text(encoding="utf-8").count("\n"), 1
                )

    def test_rejected_proposals_never_load_and_users_are_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(ps_mod, "MEMORY_DIR", root / "memory"), patch.object(
                us_mod, "DATA_USERS_DIR", root / "users"
            ):
                alice, _ = self._create(user_id="alice", content="Alice convention")
                bob, _ = self._create(user_id="bob", content="Bob convention")
                ps_mod.decide_proposal(
                    user_id="alice", proposal_id=alice["proposal_id"], decision="rejected"
                )
                ps_mod.decide_proposal(
                    user_id="bob", proposal_id=bob["proposal_id"], decision="approved"
                )

                self.assertEqual(ps_mod.list_approved_memories(user_id="alice"), [])
                self.assertEqual(
                    [memory["content"] for memory in ps_mod.list_approved_memories(user_id="bob")],
                    ["Bob convention"],
                )
                self.assertTrue(ps_mod.proposals_path("alice").exists())
                self.assertNotEqual(ps_mod.proposals_path("alice"), ps_mod.proposals_path("bob"))
                self.assertIn(
                    "Bob convention",
                    ps_mod.materialized_memory_paths("bob")["user_capsule"].read_text(
                        encoding="utf-8"
                    ),
                )
                self.assertFalse(ps_mod.materialized_memory_dir("alice").exists())

    def test_relationship_memory_materializes_to_its_own_layer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(ps_mod, "MEMORY_DIR", root / "memory"):
                proposal, _ = ps_mod.create_proposal(
                    user_id="anonymous",
                    session_id="main",
                    target="relationship_memory",
                    memory_type="behavior_preference",
                    content="Start with a concise conclusion before details.",
                    rationale="The user explicitly confirmed this collaboration preference.",
                )
                ps_mod.decide_proposal(
                    user_id="anonymous", proposal_id=proposal["proposal_id"], decision="approved"
                )
                relationship = ps_mod.materialized_memory_paths()["relationship_memory"]

                self.assertIn("# Relationship Primer", relationship.read_text(encoding="utf-8"))
                self.assertIn(proposal["proposal_id"], relationship.read_text(encoding="utf-8"))

    def test_cannot_decide_missing_or_already_decided_proposal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(ps_mod, "MEMORY_DIR", root / "memory"):
                proposal, _ = self._create()
                with self.assertRaises(ps_mod.ProposalNotFoundError):
                    ps_mod.decide_proposal(
                        user_id="anonymous", proposal_id="memprop_missing", decision="approved"
                    )
                ps_mod.decide_proposal(
                    user_id="anonymous", proposal_id=proposal["proposal_id"], decision="approved"
                )
                with self.assertRaises(ps_mod.ProposalStateError):
                    ps_mod.decide_proposal(
                        user_id="anonymous", proposal_id=proposal["proposal_id"], decision="rejected"
                    )


if __name__ == "__main__":
    unittest.main()
