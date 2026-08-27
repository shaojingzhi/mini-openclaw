"""Unit tests for the governed long-term memory proposal store."""

from __future__ import annotations

import importlib
import json
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

    def test_private_memories_are_visible_only_to_their_agent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(ps_mod, "MEMORY_DIR", root / "memory"):
                shared, _ = ps_mod.create_proposal(
                    user_id="anonymous",
                    session_id="main",
                    agent_id="lighthouse",
                    target="project_memory",
                    memory_type="project_convention",
                    content="Run backend tests before delivery.",
                    rationale="This convention applies to the shared project.",
                )
                spark, _ = ps_mod.create_proposal(
                    user_id="anonymous",
                    session_id="main",
                    agent_id="spark",
                    target="relationship_memory",
                    memory_type="behavior_preference",
                    content="Start by exploring two alternatives.",
                    rationale="The user requested this style from Spark.",
                )
                whetstone, _ = ps_mod.create_proposal(
                    user_id="anonymous",
                    session_id="main",
                    agent_id="whetstone",
                    target="agent_behavior",
                    memory_type="behavior_preference",
                    content="Always state the riskiest assumption.",
                    rationale="The user requested this behavior from Whetstone.",
                )
                for proposal in (shared, spark, whetstone):
                    ps_mod.decide_proposal(
                        user_id="anonymous",
                        proposal_id=proposal["proposal_id"],
                        decision="approved",
                    )

                spark_memories = ps_mod.list_approved_memories(
                    user_id="anonymous", agent_id="spark"
                )
                whetstone_memories = ps_mod.list_approved_memories(
                    user_id="anonymous", agent_id="whetstone"
                )
                spark_projection = ps_mod.materialized_memory_paths(
                    agent_id="spark"
                )["relationship_memory"]
                whetstone_projection = ps_mod.materialized_memory_paths(
                    agent_id="whetstone"
                )["relationship_memory"]
                spark_projection_content = spark_projection.read_text(encoding="utf-8")
                whetstone_projection_content = whetstone_projection.read_text(encoding="utf-8")

        self.assertEqual(
            {memory["proposal_id"] for memory in spark_memories},
            {shared["proposal_id"], spark["proposal_id"]},
        )
        self.assertEqual(
            {memory["proposal_id"] for memory in whetstone_memories},
            {shared["proposal_id"], whetstone["proposal_id"]},
        )
        self.assertNotEqual(spark_projection, whetstone_projection)
        self.assertIn("Start by exploring", spark_projection_content)
        self.assertNotIn("Start by exploring", whetstone_projection_content)

    def test_legacy_private_record_defaults_to_lighthouse(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(ps_mod, "MEMORY_DIR", root / "memory"):
                path = ps_mod.proposals_path()
                path.parent.mkdir(parents=True)
                path.write_text(
                    json.dumps(
                        {
                            "proposal_id": "memprop_legacy",
                            "status": "approved",
                            "target": "relationship_memory",
                            "memory_type": "behavior_preference",
                            "content": "Legacy relationship context.",
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )
                record = ps_mod.list_proposals(user_id="anonymous")[0]

        self.assertEqual(record["agent_id"], "lighthouse")
        self.assertEqual(record["visibility"], "agent_private")

    def test_projection_failure_leaves_proposal_pending(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(ps_mod, "MEMORY_DIR", root / "memory"):
                proposal, _ = self._create()
                with patch.object(ps_mod, "_materialize_records", side_effect=OSError("disk full")):
                    with self.assertRaises(OSError):
                        ps_mod.decide_proposal(
                            user_id="anonymous",
                            proposal_id=proposal["proposal_id"],
                            decision="approved",
                        )

                pending = ps_mod.list_proposals(user_id="anonymous", status="pending")
                self.assertEqual([record["proposal_id"] for record in pending], [proposal["proposal_id"]])

    def test_jsonl_commit_failure_restores_previous_projection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(ps_mod, "MEMORY_DIR", root / "memory"):
                existing, _ = self._create(content="Keep replies concise.")
                ps_mod.decide_proposal(
                    user_id="anonymous",
                    proposal_id=existing["proposal_id"],
                    decision="approved",
                )
                pending, _ = self._create(content="Always include three alternatives.")
                proposals_path = ps_mod.proposals_path()
                projection_path = ps_mod.materialized_memory_paths()["user_capsule"]
                original_records = proposals_path.read_text(encoding="utf-8")
                original_projection = projection_path.read_text(encoding="utf-8")

                with patch.object(
                    ps_mod,
                    "_commit_staged_records",
                    side_effect=OSError("json commit failed"),
                ):
                    with self.assertRaisesRegex(OSError, "json commit failed"):
                        ps_mod.decide_proposal(
                            user_id="anonymous",
                            proposal_id=pending["proposal_id"],
                            decision="approved",
                        )

                self.assertEqual(
                    proposals_path.read_text(encoding="utf-8"),
                    original_records,
                )
                self.assertEqual(
                    projection_path.read_text(encoding="utf-8"),
                    original_projection,
                )
                self.assertNotIn("Always include three alternatives.", original_projection)
                self.assertEqual(
                    [
                        record["proposal_id"]
                        for record in ps_mod.list_proposals(
                            status="pending",
                            user_id="anonymous",
                        )
                    ],
                    [pending["proposal_id"]],
                )
                memory_dir = root / "memory"
                self.assertEqual(list(memory_dir.glob(".approved_memory.stage-*")), [])
                self.assertEqual(list(memory_dir.glob(".approved_memory.backup-*")), [])
                self.assertEqual(list(memory_dir.glob(".memory_proposals.jsonl.stage-*")), [])

    def test_startup_recovery_rebuilds_projection_and_removes_transaction_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(ps_mod, "MEMORY_DIR", root / "memory"):
                proposal, _ = self._create(content="Recover this approved memory.")
                ps_mod.decide_proposal(
                    user_id="anonymous",
                    proposal_id=proposal["proposal_id"],
                    decision="approved",
                )
                memory_dir = root / "memory"
                projection = ps_mod.materialized_memory_paths()["user_capsule"]
                projection.write_text("interrupted projection\n", encoding="utf-8")
                (memory_dir / ".approved_memory.backup-interrupted").mkdir()
                (memory_dir / ".approved_memory.stage-interrupted").mkdir()
                (memory_dir / ".memory_proposals.jsonl.stage-interrupted").write_text(
                    "incomplete",
                    encoding="utf-8",
                )

                recovered = ps_mod.recover_memory_projections()
                rebuilt = projection.read_text(encoding="utf-8")

        self.assertIn("anonymous", recovered)
        self.assertIn("Recover this approved memory.", rebuilt)
        self.assertNotIn("interrupted projection", rebuilt)
        self.assertEqual(list(memory_dir.glob(".approved_memory.stage-*")), [])
        self.assertEqual(list(memory_dir.glob(".approved_memory.backup-*")), [])
        self.assertEqual(list(memory_dir.glob(".memory_proposals.jsonl.stage-*")), [])

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
