"""Unit tests for backend/prompt_assembler.py."""

from __future__ import annotations

import importlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Use importlib so patch.object can find module-level attributes — the
# package re-export shadow trick noted in progress.txt §Codebase Patterns
# does not bite here (prompt_assembler is not re-exported from a package
# __init__.py), but importlib is the safer habit.
pa_mod = importlib.import_module("backend.prompt_assembler")


class BuildSystemPromptTests(unittest.TestCase):
    def _seed_all(self, workspace: Path, memory: Path, *, oversized: str | None = None) -> None:
        """Write the six expected files with small, distinctive content."""
        workspace.mkdir(parents=True, exist_ok=True)
        memory.mkdir(parents=True, exist_ok=True)

        (workspace / "SKILLS_SNAPSHOT.md").write_text("SKILLS_BODY", encoding="utf-8")
        (workspace / "SOUL.md").write_text("SOUL_BODY", encoding="utf-8")
        (workspace / "IDENTITY.md").write_text("IDENTITY_BODY", encoding="utf-8")
        (workspace / "USER.md").write_text("USER_BODY", encoding="utf-8")
        (workspace / "AGENTS.md").write_text("AGENTS_BODY", encoding="utf-8")
        (memory / "MEMORY.md").write_text("MEMORY_BODY", encoding="utf-8")

        if oversized is not None:
            (workspace / oversized).write_text(
                "X" * (pa_mod.MAX_FILE_CHARS + 500), encoding="utf-8"
            )

    def test_concatenates_six_sections_in_required_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            workspace = tmp_path / "workspace"
            memory = tmp_path / "memory"
            self._seed_all(workspace, memory)

            with patch.object(pa_mod, "WORKSPACE_DIR", workspace), patch.object(
                pa_mod, "MEMORY_DIR", memory
            ):
                prompt = pa_mod.build_system_prompt()

            expected_order = [
                ("SKILLS_SNAPSHOT.md", "SKILLS_BODY"),
                ("SOUL.md", "SOUL_BODY"),
                ("IDENTITY.md", "IDENTITY_BODY"),
                ("USER.md", "USER_BODY"),
                ("AGENTS.md", "AGENTS_BODY"),
                ("MEMORY.md", "MEMORY_BODY"),
            ]

            # Each header + body appears, and they appear in the required order.
            last_pos = -1
            for display_name, body in expected_order:
                header = f"# === {display_name} ==="
                pos = prompt.find(header)
                self.assertGreater(pos, last_pos, f"{header} out of order")
                self.assertIn(body, prompt[pos:])
                last_pos = pos

    def test_truncates_oversized_file_and_appends_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            workspace = tmp_path / "workspace"
            memory = tmp_path / "memory"
            self._seed_all(workspace, memory, oversized="USER.md")

            with patch.object(pa_mod, "WORKSPACE_DIR", workspace), patch.object(
                pa_mod, "MEMORY_DIR", memory
            ):
                prompt = pa_mod.build_system_prompt()

            self.assertIn(pa_mod.TRUNCATION_MARKER, prompt)
            # The USER.md section is the one that should carry the marker.
            user_header = "# === USER.md ==="
            user_start = prompt.index(user_header)
            next_header = prompt.index("# === AGENTS.md ===", user_start)
            user_section = prompt[user_start:next_header]
            self.assertTrue(user_section.rstrip().endswith(pa_mod.TRUNCATION_MARKER))
            # And no other section grew the marker.
            self.assertEqual(prompt.count(pa_mod.TRUNCATION_MARKER), 1)

    def test_short_files_are_not_truncated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            workspace = tmp_path / "workspace"
            memory = tmp_path / "memory"
            self._seed_all(workspace, memory)

            with patch.object(pa_mod, "WORKSPACE_DIR", workspace), patch.object(
                pa_mod, "MEMORY_DIR", memory
            ):
                prompt = pa_mod.build_system_prompt()

            self.assertNotIn(pa_mod.TRUNCATION_MARKER, prompt)

    def test_missing_file_falls_back_to_placeholder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            workspace = tmp_path / "workspace"
            memory = tmp_path / "memory"
            self._seed_all(workspace, memory)
            # Remove one of the sources to simulate a missing file.
            (workspace / "USER.md").unlink()

            with patch.object(pa_mod, "WORKSPACE_DIR", workspace), patch.object(
                pa_mod, "MEMORY_DIR", memory
            ):
                prompt = pa_mod.build_system_prompt()

            self.assertIn("# === USER.md ===", prompt)
            self.assertIn(pa_mod.MISSING_FILE_PLACEHOLDER, prompt)

    def test_real_files_assemble_without_error(self) -> None:
        # Smoke test: build against the committed workspace/memory files.
        prompt = pa_mod.build_system_prompt()
        for display_name in (
            "SKILLS_SNAPSHOT.md",
            "SOUL.md",
            "IDENTITY.md",
            "USER.md",
            "AGENTS.md",
            "MEMORY.md",
        ):
            self.assertIn(f"# === {display_name} ===", prompt)


if __name__ == "__main__":
    unittest.main()
