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

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_DIR = PROJECT_ROOT / "backend" / "workspace"
MEMORY_DIR = PROJECT_ROOT / "backend" / "memory"

MAX_FILE_CHARS = 20_000
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


def build_system_prompt() -> str:
    """Assemble the six prompt sources into a single system prompt string."""
    parts: list[str] = []
    for display_name, path in _section_paths():
        header = f"# === {display_name} ==="
        body = _maybe_truncate(_load_file(path))
        parts.append(f"{header}\n{body}")
    # Single blank line between sections; trailing newline keeps tools that
    # append text after the prompt from running into the last byte.
    return "\n\n".join(parts) + "\n"


if __name__ == "__main__":
    print(build_system_prompt())
