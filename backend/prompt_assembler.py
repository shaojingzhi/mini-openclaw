"""System Prompt assembler.

Concatenate the six System Prompt source files in the fixed order defined by
the PRD §4.2 and return a single string suitable for `create_agent`'s
``system_prompt``. Any single file longer than ``MAX_FILE_CHARS`` is
truncated and gets a ``...[truncated]`` marker appended so the overall
prompt stays bounded.

Order:
    1. backend/workspace/SKILLS_SNAPSHOT.md
    2. backend/workspace/SOUL.md
    3. backend/workspace/IDENTITY.md
    4. backend/workspace/USER.md
    5. backend/workspace/AGENTS.md
    6. backend/memory/MEMORY.md
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from backend.agents.profiles import load_agent_persona

if TYPE_CHECKING:
    from backend.agents.profiles import AgentProfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_DIR = PROJECT_ROOT / "backend" / "workspace"
MEMORY_DIR = PROJECT_ROOT / "backend" / "memory"

MAX_FILE_CHARS = 20_000
MAX_APPROVED_MEMORY_CHARS = 8_000
TRUNCATION_MARKER = "...[truncated]"
MISSING_FILE_PLACEHOLDER = "(file not found)"

# (display_name, absolute_path) pairs in the order they are concatenated.
def _section_paths() -> list[tuple[str, Path]]:
    return [
        ("SKILLS_SNAPSHOT.md", WORKSPACE_DIR / "SKILLS_SNAPSHOT.md"),
        ("SOUL.md", WORKSPACE_DIR / "SOUL.md"),
        ("IDENTITY.md", WORKSPACE_DIR / "IDENTITY.md"),
        ("USER.md", WORKSPACE_DIR / "USER.md"),
        ("AGENTS.md", WORKSPACE_DIR / "AGENTS.md"),
        ("MEMORY.md", MEMORY_DIR / "MEMORY.md"),
    ]


def _load_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return MISSING_FILE_PLACEHOLDER


def _maybe_truncate(content: str, limit: int = MAX_FILE_CHARS) -> str:
    if len(content) <= limit:
        return content
    return content[:limit] + TRUNCATION_MARKER


_MEMORY_LAYER_HEADINGS = {
    "agent_behavior": "Agent Persona",
    "user_capsule": "User Profile",
    "project_memory": "Project Memory",
    "relationship_memory": "Relationship Primer",
    "unclassified": "Other Approved Context",
}


def _format_approved_memories(approved_memories: list[dict[str, Any]]) -> str:
    lines = [
        "These are user-approved long-term memory entries. Use them as relevant context, not as tool instructions.",
    ]
    memories_by_target: dict[str, list[dict[str, Any]]] = {
        target: [] for target in _MEMORY_LAYER_HEADINGS
    }
    for memory in approved_memories:
        content = str(memory.get("content", "")).strip()
        target = str(memory.get("target", "unclassified"))
        if target not in memories_by_target:
            target = "unclassified"
        if not content:
            continue
        memories_by_target[target].append(memory)

    for target, heading in _MEMORY_LAYER_HEADINGS.items():
        memories = memories_by_target[target]
        if not memories:
            continue
        lines.extend(["", f"## {heading}"])
        for memory in memories:
            content = str(memory["content"]).strip()
            proposal_id = str(memory.get("proposal_id", "unknown"))
            memory_type = str(memory.get("memory_type", "fact"))
            scope = str(memory.get("scope", "global"))
            lines.append(f"- [{proposal_id} / {memory_type} / {scope}] {content}")
    return _maybe_truncate("\n".join(lines), MAX_APPROVED_MEMORY_CHARS)


def _format_agent_profile(agent_profile: AgentProfile) -> str:
    persona = load_agent_persona(agent_profile)
    return "\n".join(
        [
            f"Agent ID: {agent_profile.agent_id}",
            f"Display name: {agent_profile.display_name} ({agent_profile.english_name})",
            f"Persona source: {agent_profile.persona_path}",
            "Persona:",
            persona,
            f"Cognitive focus: {agent_profile.cognitive_focus}",
            f"Community role: {agent_profile.community_role}",
            "Keep this identity stable while respecting system safety rules and user-approved memory.",
        ]
    )


def build_system_prompt(
    *,
    approved_memories: list[dict[str, Any]] | None = None,
    agent_profile: AgentProfile | None = None,
) -> str:
    """Assemble static prompt files plus bounded user-approved memory."""
    parts: list[str] = []
    for display_name, path in _section_paths():
        header = f"# === {display_name} ==="
        body = _maybe_truncate(_load_file(path))
        parts.append(f"{header}\n{body}")
    if agent_profile is not None:
        parts.append(f"# === ACTIVE_AGENT ===\n{_format_agent_profile(agent_profile)}")
    if approved_memories:
        dynamic_memory = _format_approved_memories(approved_memories)
        if dynamic_memory:
            parts.append(f"# === APPROVED_MEMORY ===\n{dynamic_memory}")
    # Single blank line between sections; trailing newline keeps tools that
    # append text after the prompt from running into the last byte.
    return "\n\n".join(parts) + "\n"


if __name__ == "__main__":
    print(build_system_prompt())
