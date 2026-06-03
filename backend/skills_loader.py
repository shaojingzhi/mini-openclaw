"""Skills bootstrap.

Scan `backend/skills/*/SKILL.md`, parse YAML frontmatter for `name` /
`description`, and emit the `<available_skills>` XML snapshot that is
concatenated into the system prompt by `prompt_assembler` (US-011).

The snapshot is also persisted to `backend/workspace/SKILLS_SNAPSHOT.md`
so it can be inspected by the frontend Memory/Skills panes.
"""

from __future__ import annotations

import re
from pathlib import Path
from xml.sax.saxutils import escape

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = PROJECT_ROOT / "backend" / "skills"
SNAPSHOT_PATH = PROJECT_ROOT / "backend" / "workspace" / "SKILLS_SNAPSHOT.md"

# `---\n...\n---` at the very top of the file, with the trailing newline optional.
_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", re.DOTALL)


def _parse_frontmatter(text: str) -> dict[str, object]:
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}
    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def _discover_skills(skills_dir: Path) -> list[dict[str, str]]:
    if not skills_dir.exists() or not skills_dir.is_dir():
        return []

    found: list[dict[str, str]] = []
    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        try:
            text = skill_md.read_text(encoding="utf-8")
        except OSError:
            continue
        meta = _parse_frontmatter(text)

        folder = skill_md.parent.name
        name = str(meta.get("name") or folder).strip()
        description = str(meta.get("description") or "").strip()
        # Location is always relative to PROJECT_ROOT so the agent's read_file
        # tool (root_dir=PROJECT_ROOT, see backend/tools/read_file.py) can
        # resolve it directly.
        location = f"./backend/skills/{folder}/SKILL.md"

        found.append({"name": name, "description": description, "location": location})
    return found


def build_skills_snapshot(
    skills_dir: Path | None = None,
    *,
    write: bool = True,
    snapshot_path: Path | None = None,
) -> str:
    """Return the `<available_skills>` XML for all discovered SKILL.md files.

    Args:
        skills_dir: directory to scan; defaults to `backend/skills/`.
        write: when True, also persist the snapshot to `snapshot_path`.
        snapshot_path: override the default `backend/workspace/SKILLS_SNAPSHOT.md`.
    """
    target_dir = skills_dir if skills_dir is not None else SKILLS_DIR
    skills = _discover_skills(target_dir)

    lines: list[str] = ["<available_skills>"]
    for skill in skills:
        lines.append("  <skill>")
        lines.append(f"    <name>{escape(skill['name'])}</name>")
        lines.append(f"    <description>{escape(skill['description'])}</description>")
        lines.append(f"    <location>{escape(skill['location'])}</location>")
        lines.append("  </skill>")
    lines.append("</available_skills>")
    snapshot = "\n".join(lines) + "\n"

    if write:
        out = snapshot_path if snapshot_path is not None else SNAPSHOT_PATH
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(snapshot, encoding="utf-8")

    return snapshot


if __name__ == "__main__":
    print(build_skills_snapshot())
