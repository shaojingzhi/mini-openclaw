"""Deterministic mention routing with a stable default host."""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.agents.profiles import DEFAULT_AGENT_ID, AgentId, list_agent_profiles


@dataclass(frozen=True, slots=True)
class RouteDecision:
    selected_agent_id: AgentId
    route_reason: str
    matched_mention: str | None = None


_ALIAS_TO_AGENT = {
    alias.casefold(): profile.agent_id
    for profile in list_agent_profiles()
    for alias in profile.aliases
}
_ALIASES_PATTERN = "|".join(
    re.escape(alias) for alias in sorted(_ALIAS_TO_AGENT, key=len, reverse=True)
)
_MENTION_PATTERN = re.compile(
    rf"@(?P<alias>{_ALIASES_PATTERN})(?![A-Za-z0-9_-])",
    re.IGNORECASE,
)


def route_message(message: str) -> RouteDecision:
    match = _MENTION_PATTERN.search(message)
    if match is None:
        return RouteDecision(
            selected_agent_id=DEFAULT_AGENT_ID,
            route_reason="default_host",
        )

    alias = match.group("alias")
    return RouteDecision(
        selected_agent_id=_ALIAS_TO_AGENT[alias.casefold()],
        route_reason="explicit_mention",
        matched_mention=match.group(0),
    )


__all__ = ["RouteDecision", "route_message"]
