"""Integration tests for the /api/files endpoints."""

from __future__ import annotations

import importlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

app_mod = importlib.import_module("backend.app")


class ApiFilesTests(unittest.TestCase):
    def test_get_file_reads_allowed_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            memory_dir = project_root / "backend" / "memory"
            workspace_dir = project_root / "backend" / "workspace"
            skills_dir = project_root / "backend" / "skills"
            for directory in (memory_dir, workspace_dir, skills_dir):
                directory.mkdir(parents=True, exist_ok=True)
            target = workspace_dir / "AGENTS.md"
            target.write_text("hello file api", encoding="utf-8")

            with patch.object(app_mod, "PROJECT_ROOT", project_root), patch.object(
                app_mod,
                "ALLOWED_FILE_ROOTS",
                (memory_dir, workspace_dir, skills_dir),
            ):
                client = TestClient(app_mod.app)
                response = client.get(
                    "/api/files", params={"path": "backend/workspace/AGENTS.md"}
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"path": "backend/workspace/AGENTS.md", "content": "hello file api"},
        )

    def test_post_file_writes_allowed_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            memory_dir = project_root / "backend" / "memory"
            workspace_dir = project_root / "backend" / "workspace"
            skills_dir = project_root / "backend" / "skills"
            for directory in (memory_dir, workspace_dir, skills_dir):
                directory.mkdir(parents=True, exist_ok=True)

            with patch.object(app_mod, "PROJECT_ROOT", project_root), patch.object(
                app_mod,
                "ALLOWED_FILE_ROOTS",
                (memory_dir, workspace_dir, skills_dir),
            ):
                client = TestClient(app_mod.app)
                response = client.post(
                    "/api/files",
                    json={
                        "path": "backend/memory/MEMORY.md",
                        "content": "saved content",
                    },
                )
                written = (memory_dir / "MEMORY.md").read_text(encoding="utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"path": "backend/memory/MEMORY.md", "content": "saved content"},
        )
        self.assertEqual(written, "saved content")

    def test_rejects_path_traversal_and_outside_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            memory_dir = project_root / "backend" / "memory"
            workspace_dir = project_root / "backend" / "workspace"
            skills_dir = project_root / "backend" / "skills"
            for directory in (memory_dir, workspace_dir, skills_dir):
                directory.mkdir(parents=True, exist_ok=True)

            with patch.object(app_mod, "PROJECT_ROOT", project_root), patch.object(
                app_mod,
                "ALLOWED_FILE_ROOTS",
                (memory_dir, workspace_dir, skills_dir),
            ):
                client = TestClient(app_mod.app)
                traversal_response = client.get(
                    "/api/files",
                    params={"path": "backend/workspace/../sessions/main.json"},
                )
                outside_response = client.post(
                    "/api/files",
                    json={"path": "backend/sessions/main.json", "content": "nope"},
                )

        self.assertEqual(traversal_response.status_code, 403)
        self.assertEqual(outside_response.status_code, 403)

    def test_missing_allowed_file_returns_404(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            memory_dir = project_root / "backend" / "memory"
            workspace_dir = project_root / "backend" / "workspace"
            skills_dir = project_root / "backend" / "skills"
            for directory in (memory_dir, workspace_dir, skills_dir):
                directory.mkdir(parents=True, exist_ok=True)

            with patch.object(app_mod, "PROJECT_ROOT", project_root), patch.object(
                app_mod,
                "ALLOWED_FILE_ROOTS",
                (memory_dir, workspace_dir, skills_dir),
            ):
                client = TestClient(app_mod.app)
                response = client.get(
                    "/api/files", params={"path": "backend/workspace/MISSING.md"}
                )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "file not found")


if __name__ == "__main__":
    unittest.main()
