"""Unit tests for the read_file agent tool (US-007)."""

from __future__ import annotations

import unittest

from backend.tools.read_file import PROJECT_ROOT, read_file


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


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
