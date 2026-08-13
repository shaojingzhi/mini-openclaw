"""Tests for deterministic community routing and bounded handoffs."""

from __future__ import annotations

import json
import unittest

from fastapi.testclient import TestClient

from backend.agents.profiles import get_agent_profile, list_agent_profiles
from backend.agents.router import route_message
from backend.app import app
from backend.tools.request_handoff import build_request_handoff_tool


class AgentRoutingTests(unittest.TestCase):
    def test_agents_api_exposes_interview_facing_profile_metadata(self) -> None:
        response = TestClient(app).get("/api/agents")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [agent["agent_id"] for agent in response.json()["agents"]],
            ["lighthouse", "spark", "whetstone"],
        )
        self.assertTrue(response.json()["agents"][0]["is_default"])

    def test_registry_contains_three_stable_personas(self) -> None:
        profiles = list_agent_profiles()

        self.assertEqual(
            [profile.agent_id for profile in profiles],
            ["lighthouse", "spark", "whetstone"],
        )
        self.assertEqual(get_agent_profile("SPARK").display_name, "火花")
        self.assertEqual(get_agent_profile("whetstone").display_name, "砥石")

    def test_router_defaults_to_lighthouse_and_honors_first_known_mention(self) -> None:
        default = route_message("Help me review this project")
        direct = route_message("请 @火花 找一些替代方案")
        english = route_message("@Whetstone, challenge this argument")

        self.assertEqual(default.selected_agent_id, "lighthouse")
        self.assertEqual(default.route_reason, "default_host")
        self.assertEqual(direct.selected_agent_id, "spark")
        self.assertEqual(direct.matched_mention, "@火花")
        self.assertEqual(english.selected_agent_id, "whetstone")
        self.assertEqual(english.route_reason, "explicit_mention")

    def test_handoff_tool_accepts_only_one_allowed_target(self) -> None:
        requested: list[dict[str, object]] = []
        tool = build_request_handoff_tool(
            from_agent_id="lighthouse",
            allowed_targets=("spark", "whetstone"),
            on_handoff_requested=requested.append,
        )

        first = json.loads(
            tool.invoke(
                {
                    "target_agent_id": "whetstone",
                    "task": "Check the interview claim.",
                    "reason": "The claim needs stricter validation.",
                }
            )
        )
        second = json.loads(
            tool.invoke(
                {
                    "target_agent_id": "spark",
                    "task": "Find alternatives.",
                    "reason": "Broaden the answer.",
                }
            )
        )

        self.assertTrue(first["accepted"])
        self.assertFalse(second["accepted"])
        self.assertEqual(len(requested), 1)
        self.assertEqual(requested[0]["to_agent_id"], "whetstone")


if __name__ == "__main__":
    unittest.main()
