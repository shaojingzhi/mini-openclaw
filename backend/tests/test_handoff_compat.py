"""Tests for the tool-free compatibility handoff decision format."""

from __future__ import annotations

import unittest

from backend.agents.handoff_compat import (
    is_explicit_collaboration_request,
    parse_compatibility_handoff_decision,
)
from backend.agents.profiles import get_agent_profile


class HandoffCompatibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.lighthouse = get_agent_profile("lighthouse")

    def test_explicit_collaboration_request_matches_the_demo_phrase(self) -> None:
        self.assertTrue(is_explicit_collaboration_request("帮我把另外两个小伙伴叫出来好不好"))
        self.assertTrue(is_explicit_collaboration_request("请把这件事交给砥石审查"))
        self.assertFalse(is_explicit_collaboration_request("帮我总结这段对话"))

    def test_valid_decision_accepts_only_allowed_target(self) -> None:
        decision = parse_compatibility_handoff_decision(
            '{"handoff": true, "target_agent_id": "whetstone", '
            '"task": "Review the claim.", "reason": "The user asked for a critique."}',
            profile=self.lighthouse,
        )

        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertEqual(decision.target_agent_id, "whetstone")

    def test_malformed_or_disallowed_decision_cannot_trigger_handoff(self) -> None:
        self.assertIsNone(
            parse_compatibility_handoff_decision(
                '{"handoff": true, "target_agent_id": "lighthouse", "task": "x", "reason": "y"}',
                profile=self.lighthouse,
            )
        )
        self.assertIsNone(parse_compatibility_handoff_decision("I choose spark", profile=self.lighthouse))


if __name__ == "__main__":
    unittest.main()
