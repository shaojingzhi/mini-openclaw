"""Invocation-scoped tool for one explicit, runtime-governed agent handoff."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Literal

from langchain_core.tools import BaseTool, tool

from backend.agents.profiles import AgentId, get_agent_profile

HandoffRequestedCallback = Callable[[dict[str, Any]], None]


def _required_text(value: str, *, name: str, limit: int) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} must not be empty")
    if len(normalized) > limit:
        raise ValueError(f"{name} must be at most {limit} characters")
    return normalized


def build_request_handoff_tool(
    *,
    from_agent_id: AgentId,
    allowed_targets: tuple[AgentId, ...],
    on_handoff_requested: HandoffRequestedCallback | None = None,
) -> BaseTool:
    """Build a tool that accepts at most one handoff request per agent run."""
    handoff_created = False

    @tool("request_agent_handoff")
    def request_agent_handoff(
        target_agent_id: Literal["lighthouse", "spark", "whetstone"],
        task: str,
        reason: str,
    ) -> str:
        """Ask one other community agent to answer the current user request.

        Use only when the target agent's cognitive perspective materially improves
        the answer. The runtime allows one handoff, so provide a self-contained task
        and a concise user-visible reason.
        """
        nonlocal handoff_created
        target_profile = get_agent_profile(target_agent_id)
        if target_profile.agent_id not in allowed_targets:
            return json.dumps(
                {
                    "accepted": False,
                    "message": f"Handoff to {target_agent_id} is not allowed for {from_agent_id}.",
                }
            )
        if handoff_created:
            return json.dumps(
                {
                    "accepted": False,
                    "message": "This run already requested its one allowed handoff.",
                }
            )

        request = {
            "from_agent_id": from_agent_id,
            "to_agent_id": target_profile.agent_id,
            "task": _required_text(task, name="task", limit=2_000),
            "reason": _required_text(reason, name="reason", limit=500),
        }
        handoff_created = True
        if on_handoff_requested is not None:
            on_handoff_requested(request)
        return json.dumps(
            {
                "accepted": True,
                "to_agent_id": target_profile.agent_id,
                "message": "The runtime will transfer control after this agent run.",
            },
            ensure_ascii=False,
        )

    return request_agent_handoff


__all__ = ["HandoffRequestedCallback", "build_request_handoff_tool"]
