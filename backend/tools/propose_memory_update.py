"""LangChain adapter for governed long-term memory proposals."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Literal

from langchain_core.tools import BaseTool, tool

from backend.memory.proposals_store import create_proposal

ProposalCreatedCallback = Callable[[dict[str, Any]], None]


def build_propose_memory_update_tool(
    *,
    user_id: str,
    session_id: str | None,
    on_proposal_created: ProposalCreatedCallback | None = None,
) -> BaseTool:
    """Build an invocation-scoped proposal tool for the local LangChain agent.

    The agent supplies semantic fields only. The user namespace and storage
    path are captured by the backend runtime, which makes this adapter safe to
    expose through MCP later without trusting agent-provided filesystem paths.
    """

    @tool("propose_memory_update")
    def propose_memory_update(
        target: Literal[
            "user_capsule",
            "project_memory",
            "agent_behavior",
            "relationship_memory",
        ],
        memory_type: Literal[
            "user_preference",
            "project_convention",
            "task_state",
            "behavior_preference",
        ],
        content: str,
        rationale: str,
        confidence: Literal["low", "medium", "high"] = "medium",
        signal_kind: Literal[
            "user_instructed",
            "explicit_preference",
            "repeated_feedback",
            "project_decision",
        ] = "explicit_preference",
        scope: Literal["global", "project", "task", "interview_prep"] = "global",
        source_message_id: str | None = None,
        client_request_id: str | None = None,
    ) -> str:
        """Create a pending long-term memory proposal without changing active memory.

        Use only for durable user preferences, confirmed project conventions,
        task state, or scoped behavior preferences. Do not propose one-off
        instructions, secrets, sensitive personal data, moods, or guesses.
        The user must approve a proposal before it appears in a future prompt.
        """
        proposal, created = create_proposal(
            user_id=user_id,
            session_id=session_id,
            target=target,
            memory_type=memory_type,
            content=content,
            rationale=rationale,
            confidence=confidence,
            signal_kind=signal_kind,
            scope=scope,
            source_message_id=source_message_id,
            client_request_id=client_request_id,
        )
        if created and on_proposal_created is not None:
            try:
                on_proposal_created(proposal)
            except Exception:
                pass
        return json.dumps(
            {
                "proposal_id": proposal["proposal_id"],
                "status": proposal["status"],
                "created": created,
                "message": "Pending approval; active long-term memory was not changed.",
            },
            ensure_ascii=False,
        )

    return propose_memory_update


__all__ = ["ProposalCreatedCallback", "build_propose_memory_update_tool"]
