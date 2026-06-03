"""Unit tests for backend/skills_loader.py."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.skills_loader import build_skills_snapshot

_SKILL_MD_VALID = """---
name: get_weather
description: 获取指定城市的实时天气信息
---

# get_weather

Use `fetch_url` against a free weather API and parse with `python_repl`.
"""

_SKILL_MD_NO_FRONTMATTER = """# Plain skill

This file has no YAML frontmatter at all.
"""

_SKILL_MD_NEEDS_ESCAPE = """---
name: html_escape_demo
description: handles <tags> & "quotes" in the description
---

Body.
"""


class BuildSkillsSnapshotTests(unittest.TestCase):
    def _seed(self, root: Path, folder: str, body: str) -> None:
        skill_dir = root / folder
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(body, encoding="utf-8")

    def test_emits_xml_for_discovered_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skills_dir = Path(tmp) / "skills"
            self._seed(skills_dir, "get_weather", _SKILL_MD_VALID)

            snapshot = build_skills_snapshot(skills_dir=skills_dir, write=False)

        self.assertTrue(snapshot.startswith("<available_skills>"))
        self.assertTrue(snapshot.strip().endswith("</available_skills>"))
        self.assertIn("<skill>", snapshot)
        self.assertIn("<name>get_weather</name>", snapshot)
        self.assertIn(
            "<description>获取指定城市的实时天气信息</description>",
            snapshot,
        )
        self.assertIn(
            "<location>./backend/skills/get_weather/SKILL.md</location>",
            snapshot,
        )

    def test_multiple_skills_are_sorted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skills_dir = Path(tmp) / "skills"
            self._seed(skills_dir, "zeta_skill", _SKILL_MD_VALID.replace("get_weather", "zeta_skill"))
            self._seed(skills_dir, "alpha_skill", _SKILL_MD_VALID.replace("get_weather", "alpha_skill"))

            snapshot = build_skills_snapshot(skills_dir=skills_dir, write=False)

        alpha_idx = snapshot.find("alpha_skill")
        zeta_idx = snapshot.find("zeta_skill")
        self.assertNotEqual(alpha_idx, -1)
        self.assertNotEqual(zeta_idx, -1)
        self.assertLess(alpha_idx, zeta_idx)

    def test_empty_skills_dir_returns_wrapper_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skills_dir = Path(tmp) / "skills"
            skills_dir.mkdir()

            snapshot = build_skills_snapshot(skills_dir=skills_dir, write=False)

        self.assertEqual(snapshot.strip(), "<available_skills>\n</available_skills>")
        self.assertNotIn("<skill>", snapshot)

    def test_missing_skills_dir_does_not_crash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "does_not_exist"

            snapshot = build_skills_snapshot(skills_dir=missing, write=False)

        self.assertIn("<available_skills>", snapshot)
        self.assertIn("</available_skills>", snapshot)

    def test_skill_without_frontmatter_falls_back_to_folder_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skills_dir = Path(tmp) / "skills"
            self._seed(skills_dir, "bare_skill", _SKILL_MD_NO_FRONTMATTER)

            snapshot = build_skills_snapshot(skills_dir=skills_dir, write=False)

        self.assertIn("<name>bare_skill</name>", snapshot)
        # Empty description still emits a (closed) element.
        self.assertIn("<description></description>", snapshot)

    def test_xml_special_chars_in_frontmatter_are_escaped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skills_dir = Path(tmp) / "skills"
            self._seed(skills_dir, "html_escape_demo", _SKILL_MD_NEEDS_ESCAPE)

            snapshot = build_skills_snapshot(skills_dir=skills_dir, write=False)

        self.assertIn(
            "<description>handles &lt;tags&gt; &amp; \"quotes\" in the description</description>",
            snapshot,
        )

    def test_write_persists_snapshot_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skills_dir = root / "skills"
            out = root / "workspace" / "SKILLS_SNAPSHOT.md"
            self._seed(skills_dir, "get_weather", _SKILL_MD_VALID)

            returned = build_skills_snapshot(
                skills_dir=skills_dir, write=True, snapshot_path=out
            )

            self.assertTrue(out.exists())
            persisted = out.read_text(encoding="utf-8")
            self.assertEqual(persisted, returned)
            self.assertIn("<name>get_weather</name>", persisted)


if __name__ == "__main__":
    unittest.main()
