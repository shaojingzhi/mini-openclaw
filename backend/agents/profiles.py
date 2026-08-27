"""Stable profiles for Mini-OpenClaw's interview-sized agent community."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

AgentId = Literal["lighthouse", "spark", "whetstone"]
DEFAULT_AGENT_ID: AgentId = "lighthouse"


@dataclass(frozen=True, slots=True)
class AgentProfile:
    agent_id: AgentId
    display_name: str
    english_name: str
    aliases: tuple[str, ...]
    persona_path: str
    cognitive_focus: str
    community_role: str
    accent: str
    allowed_handoff_targets: tuple[AgentId, ...] = ()


AGENT_PROFILES: dict[AgentId, AgentProfile] = {
    "lighthouse": AgentProfile(
        agent_id="lighthouse",
        display_name="灯塔",
        english_name="Lighthouse",
        aliases=("灯塔", "lighthouse"),
        persona_path="backend/agents/personas/lighthouse.md",
        cognitive_focus="The user's actual goal, prior decisions, and continuity across turns.",
        community_role="Default host who maintains context and coordinates another perspective when useful.",
        accent="emerald",
        allowed_handoff_targets=("spark", "whetstone"),
    ),
    "spark": AgentProfile(
        agent_id="spark",
        display_name="火花",
        english_name="Spark",
        aliases=("火花", "spark"),
        persona_path="backend/agents/personas/spark.md",
        cognitive_focus="Evidence gaps, external information, alternatives, and overlooked opportunities.",
        community_role="Scout who broadens the option space with evidence-backed discoveries.",
        accent="amber",
    ),
    "whetstone": AgentProfile(
        agent_id="whetstone",
        display_name="砥石",
        english_name="Whetstone",
        aliases=("砥石", "whetstone"),
        persona_path="backend/agents/personas/whetstone.md",
        cognitive_focus="Assumptions, contradictions, risks, over-promises, and missing validation.",
        community_role="Critic who improves decisions and deliverables without becoming hostile.",
        accent="sky",
    ),
}


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class PersonaLoadError(RuntimeError):
    """Raised when an active agent's versioned persona source is unavailable."""


def load_agent_persona(agent_profile: AgentProfile) -> str:
    """Load the active agent's persona without silently falling back to empty text."""
    path = PROJECT_ROOT / agent_profile.persona_path
    try:
        content = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise PersonaLoadError(
            f"Persona file for {agent_profile.agent_id} is unavailable: {agent_profile.persona_path}"
        ) from exc
    if not content:
        raise PersonaLoadError(
            f"Persona file for {agent_profile.agent_id} is empty: {agent_profile.persona_path}"
        )
    return content


def get_agent_profile(agent_id: str) -> AgentProfile:
    normalized = agent_id.strip().casefold()
    if normalized not in AGENT_PROFILES:
        choices = ", ".join(AGENT_PROFILES)
        raise ValueError(f"agent_id must be one of: {choices}")
    return AGENT_PROFILES[cast(AgentId, normalized)]


def normalize_agent_id(agent_id: str | None) -> AgentId:
    return get_agent_profile(agent_id or DEFAULT_AGENT_ID).agent_id


def list_agent_profiles() -> tuple[AgentProfile, ...]:
    return tuple(AGENT_PROFILES.values())


__all__ = [
    "AGENT_PROFILES",
    "DEFAULT_AGENT_ID",
    "AgentId",
    "AgentProfile",
    "PersonaLoadError",
    "get_agent_profile",
    "list_agent_profiles",
    "load_agent_persona",
    "normalize_agent_id",
]
