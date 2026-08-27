"""Agent identities, routing, and bounded collaboration primitives."""

from backend.agents.profiles import (
    AGENT_PROFILES,
    DEFAULT_AGENT_ID,
    AgentId,
    AgentProfile,
    get_agent_profile,
    list_agent_profiles,
)
from backend.agents.router import RouteDecision, route_message

__all__ = [
    "AGENT_PROFILES",
    "DEFAULT_AGENT_ID",
    "AgentId",
    "AgentProfile",
    "RouteDecision",
    "get_agent_profile",
    "list_agent_profiles",
    "route_message",
]
