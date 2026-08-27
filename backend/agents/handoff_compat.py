"""Tool-free compatibility path for explicit user-requested handoffs.

Some OpenAI-compatible gateways can produce normal assistant text but do not
implement the ``tool_calls`` / ``role=tool`` round trip required by LangChain.
This module deliberately does not pretend that a text response is a tool call:
it recognizes an explicit request for a teammate, then validates a small JSON
coordination decision before the normal runtime handoff is allowed to start.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from backend.agents.profiles import AgentId, AgentProfile


MAX_HANDOFF_TASK_CHARS = 2_000
MAX_HANDOFF_REASON_CHARS = 500

_EXPLICIT_COLLABORATION_PATTERN = re.compile(
    r"(?:"
    r"(?:(?:叫|喊).{0,12}(?:小伙伴|伙伴|朋友)|(?:小伙伴|伙伴|朋友).{0,12}(?:叫|喊))"
    r"|(?:交给|转交给|转给).{0,12}(?:灯塔|火花|砥石|lighthouse|spark|whetstone)"
    r"|(?:请|让|找).{0,12}(?:灯塔|火花|砥石|lighthouse|spark|whetstone).{0,12}(?:接手|帮忙|看看|审查|评估)"
    r")",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class CompatibilityHandoffDecision:
    """A validated coordination decision generated without provider tools."""

    target_agent_id: AgentId
    task: str
    reason: str


def is_explicit_collaboration_request(message: str) -> bool:
    """Return whether the user explicitly asked to bring in a teammate."""
    return bool(_EXPLICIT_COLLABORATION_PATTERN.search(message))


def compatibility_decision_prompt(*, profile: AgentProfile, message: str) -> str:
    """Ask for JSON only, keeping the compatibility request tool-free."""
    targets = ", ".join(profile.allowed_handoff_targets)
    return "\n".join(
        [
            "You are a coordination-only compatibility step for Mini-OpenClaw.",
            "The current gateway may not support OpenAI function calling. Do not call tools.",
            "Decide only whether the user explicitly asked the current host to invite or transfer work to one teammate.",
            f"The current host is {profile.agent_id}. Allowed target IDs: {targets}.",
            "The runtime can invite exactly one teammate. If the user asks for multiple unnamed teammates, choose the one whose role best fits the request.",
            "Reply with JSON only. Use exactly one of these shapes:",
            '{"handoff": true, "target_agent_id": "spark", "task": "...", "reason": "..."}',
            '{"handoff": false}',
            "Do not include markdown fences or extra text.",
            "User message:",
            json.dumps(message, ensure_ascii=False),
        ]
    )


def parse_compatibility_handoff_decision(
    content: Any,
    *,
    profile: AgentProfile,
) -> CompatibilityHandoffDecision | None:
    """Validate a JSON-only decision; malformed output never triggers a handoff."""
    if not isinstance(content, str):
        return None
    normalized = content.strip()
    if normalized.startswith("```") and normalized.endswith("```"):
        normalized = normalized.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        payload = json.loads(normalized)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or payload.get("handoff") is not True:
        return None

    target_agent_id = payload.get("target_agent_id")
    task = payload.get("task")
    reason = payload.get("reason")
    if (
        not isinstance(target_agent_id, str)
        or target_agent_id not in profile.allowed_handoff_targets
        or not isinstance(task, str)
        or not isinstance(reason, str)
    ):
        return None
    task = task.strip()
    reason = reason.strip()
    if (
        not task
        or not reason
        or len(task) > MAX_HANDOFF_TASK_CHARS
        or len(reason) > MAX_HANDOFF_REASON_CHARS
    ):
        return None
    return CompatibilityHandoffDecision(
        target_agent_id=target_agent_id,
        task=task,
        reason=reason,
    )


__all__ = [
    "CompatibilityHandoffDecision",
    "compatibility_decision_prompt",
    "is_explicit_collaboration_request",
    "parse_compatibility_handoff_decision",
]
