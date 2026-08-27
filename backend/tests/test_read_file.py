"""Unit tests for the read_file agent tool (US-007)."""

from __future__ import annotations

import importlib
import unittest
from unittest.mock import Mock, patch

read_file_mod = importlib.import_module("backend.tools.read_file")

PROJECT_ROOT = read_file_mod.PROJECT_ROOT
read_file = read_file_mod.read_file


class ReadFileToolTests(unittest.TestCase):
    def test_reads_file_inside_project_root(self) -> None:
        # backend/app.py is a known-good file committed to the project.
        out = read_file.invoke({"file_path": "backend/app.py"})
        expected = (PROJECT_ROOT / "backend" / "app.py").read_text(encoding="utf-8")
        self.assertEqual(out, expected)

    def test_rejects_absolute_path_outside_root(self) -> None:
        out = read_file.invoke({"file_path": "/etc/passwd"})
        self.assertIn("Access denied", out)
        # /etc/passwd on Unix always contains "root:" — the tool must NOT
        # have read it.
        self.assertNotIn("root:", out)

    def test_rejects_relative_traversal_outside_root(self) -> None:
        # ../../etc/passwd resolves outside PROJECT_ROOT regardless of
        # whether the destination file exists, so the path validator
        # rejects it before any read is attempted.
        out = read_file.invoke({"file_path": "../../etc/passwd"})
        self.assertIn("Access denied", out)

    def test_reports_missing_file_inside_root(self) -> None:
        out = read_file.invoke(
            {"file_path": "backend/this_file_definitely_does_not_exist.md"}
        )
        # Inside-root miss is a distinct error from outside-root denial.
        self.assertIn("no such file", out)
        self.assertNotIn("Access denied", out)

    def test_scoped_tool_allows_own_private_projection(self) -> None:
        scoped = read_file_mod.build_read_file_tool(agent_id="spark")
        own_path = "backend/memory/approved_memory/agents/spark/RELATIONSHIP.md"
        reader = Mock()
        reader.invoke.return_value = "spark memory"

        with patch.object(read_file_mod, "_READ_FILE_TOOL", reader):
            out = scoped.invoke({"file_path": own_path})

        self.assertEqual(out, "spark memory")
        reader.invoke.assert_called_once_with({"file_path": own_path})

    def test_scoped_tool_rejects_other_agent_private_projection(self) -> None:
        scoped = read_file_mod.build_read_file_tool(agent_id="spark")
        private_paths = (
            "backend/memory/approved_memory/agents/whetstone/RELATIONSHIP.md",
            "backend/memory/approved_memory/agents/spark/../whetstone/RELATIONSHIP.md",
            "backend/memory/approved_memory/agents/",
        )
        reader = Mock()

        with patch.object(read_file_mod, "_READ_FILE_TOOL", reader):
            for private_path in private_paths:
                with self.subTest(private_path=private_path):
                    out = scoped.invoke({"file_path": private_path})
                    self.assertEqual(out, read_file_mod.PRIVATE_MEMORY_BLOCKED_MESSAGE)

        reader.invoke.assert_not_called()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
