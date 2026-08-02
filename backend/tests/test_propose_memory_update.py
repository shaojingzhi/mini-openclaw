"""Tests for the LangChain adapter around the memory proposal service."""

from __future__ import annotations

import importlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ps_mod = importlib.import_module("backend.memory.proposals_store")
tool_mod = importlib.import_module("backend.tools.propose_memory_update")
us_mod = importlib.import_module("backend.user_state")


class ProposeMemoryUpdateToolTests(unittest.TestCase):
    def test_tool_creates_pending_proposal_and_notifies_once(self) -> None:
        created: list[dict[str, object]] = []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(ps_mod, "MEMORY_DIR", root / "memory"), patch.object(
                us_mod, "DATA_USERS_DIR", root / "users"
            ):
                tool = tool_mod.build_propose_memory_update_tool(
                    user_id="alice",
                    session_id="session-1",
                    on_proposal_created=created.append,
                )
                tool_input = {
                    "target": "project_memory",
                    "memory_type": "project_convention",
                    "content": "Keep the frontend typecheck in the release checklist.",
                    "rationale": "The user requested this convention.",
                    "confidence": "high",
                    "signal_kind": "user_instructed",
                    "scope": "project",
                }
                first = json.loads(tool.invoke(tool_input))
                duplicate = json.loads(tool.invoke(tool_input))

                self.assertTrue(first["created"])
                self.assertFalse(duplicate["created"])
                self.assertEqual(first["status"], "pending")
                self.assertEqual(len(created), 1)
                self.assertEqual(created[0]["session_id"], "session-1")
                self.assertEqual(ps_mod.list_approved_memories(user_id="alice"), [])


if __name__ == "__main__":
    unittest.main()
