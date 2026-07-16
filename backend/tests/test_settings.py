"""Unit tests for typed runtime settings."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.settings import DEFAULT_CORS_ORIGINS, PROJECT_ROOT, get_settings


class RuntimeSettingsTests(unittest.TestCase):
    def tearDown(self) -> None:
        get_settings.cache_clear()

    def test_defaults_are_typed_and_demo_friendly(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            get_settings.cache_clear()
            settings = get_settings()

        self.assertEqual(settings.openai_api_key, "EMPTY")
        self.assertEqual(settings.openai_base_url, None)
        self.assertEqual(settings.openai_model, "gpt-4o-mini")
        self.assertEqual(settings.backend_host, "0.0.0.0")
        self.assertEqual(settings.backend_port, 8002)
        self.assertEqual(settings.cors_origins, DEFAULT_CORS_ORIGINS)
        self.assertEqual(
            settings.knowledge_dir,
            PROJECT_ROOT / "backend" / "knowledge",
        )
        self.assertEqual(
            settings.graph_path,
            PROJECT_ROOT / "backend" / "data" / "graph" / "knowledge_graph.json",
        )
        self.assertEqual(settings.retrieval_top_k, 5)
        self.assertEqual(settings.python_repl_timeout_seconds, 3.0)
        self.assertEqual(settings.langsmith_api_key, None)
        self.assertEqual(settings.langsmith_endpoint, None)
        self.assertEqual(settings.langsmith_project, "mini-openclaw-evals")

    def test_environment_overrides_are_parsed(self) -> None:
        env = {
            "OPENAI_API_KEY": "test-key",
            "OPENAI_BASE_URL": "http://127.0.0.1:1234/v1",
            "OPENAI_MODEL": "local-model",
            "MINI_OPENCLAW_BACKEND_PORT": "9000",
            "MINI_OPENCLAW_CORS_ORIGINS": "http://one.test, http://two.test",
            "MINI_OPENCLAW_KNOWLEDGE_DIR": "custom/knowledge",
            "MINI_OPENCLAW_GRAPH_PATH": "/tmp/custom-graph.json",
            "MINI_OPENCLAW_RETRIEVAL_TOP_K": "7",
            "MINI_OPENCLAW_PYTHON_REPL_TIMEOUT_SECONDS": "1.5",
            "MINI_OPENCLAW_PYTHON_REPL_MEMORY_LIMIT_BYTES": "123456",
            "LANGSMITH_API_KEY": "ls-key",
            "LANGSMITH_ENDPOINT": "https://ls.example/v1",
            "MINI_OPENCLAW_LANGSMITH_PROJECT": "mini-openclaw-ls",
        }
        with patch.dict(os.environ, env, clear=True):
            get_settings.cache_clear()
            settings = get_settings()

        self.assertEqual(settings.openai_api_key, "test-key")
        self.assertEqual(settings.openai_base_url, "http://127.0.0.1:1234/v1")
        self.assertEqual(settings.openai_model, "local-model")
        self.assertEqual(settings.backend_port, 9000)
        self.assertEqual(settings.cors_origins, ("http://one.test", "http://two.test"))
        self.assertEqual(settings.knowledge_dir, PROJECT_ROOT / "custom" / "knowledge")
        self.assertEqual(settings.graph_path, Path("/tmp/custom-graph.json"))
        self.assertEqual(settings.retrieval_top_k, 7)
        self.assertEqual(settings.python_repl_timeout_seconds, 1.5)
        self.assertEqual(settings.python_repl_memory_limit_bytes, 123456)
        self.assertEqual(settings.langsmith_api_key, "ls-key")
        self.assertEqual(settings.langsmith_endpoint, "https://ls.example/v1")
        self.assertEqual(settings.langsmith_project, "mini-openclaw-ls")


if __name__ == "__main__":
    unittest.main()
