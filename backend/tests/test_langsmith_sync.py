"""Unit tests for LangSmith eval dataset synchronization."""

from __future__ import annotations

import types
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.evals import langsmith_sync as sync_mod


class _FakeDataset:
    def __init__(self, dataset_id: str, example_count: int = 0) -> None:
        self.id = dataset_id
        self.example_count = example_count


class _FakeClient:
    def __init__(self, existing: dict[str, _FakeDataset] | None = None) -> None:
        self._existing = existing or {}
        self.created: list[dict[str, object]] = []
        self.created_examples: list[dict[str, object]] = []

    def has_dataset(self, dataset_name: str) -> bool:
        return dataset_name in self._existing

    def read_dataset(self, *, dataset_name: str):
        return self._existing[dataset_name]

    def create_dataset(self, **kwargs):
        dataset_name = str(kwargs["dataset_name"])
        dataset = _FakeDataset(f"{dataset_name}-id")
        self._existing[dataset_name] = dataset
        self.created.append(kwargs)
        return dataset

    def create_examples(self, **kwargs):
        self.created_examples.append(kwargs)
        dataset_id = kwargs.get("dataset_id")
        examples = list(kwargs.get("examples", []))
        for dataset in self._existing.values():
            if dataset.id == dataset_id:
                dataset.example_count = len(examples)
        return {"count": len(examples)}


class LangSmithSyncTests(unittest.TestCase):
    def tearDown(self) -> None:
        sync_mod.get_settings.cache_clear()

    def test_skips_when_langsmith_is_unconfigured(self) -> None:
        fake_settings = types.SimpleNamespace(
            langsmith_api_key=None,
            langsmith_endpoint=None,
            langsmith_project="mini-openclaw-evals",
        )
        with patch.object(sync_mod, "get_settings", return_value=fake_settings):
            result = sync_mod.sync_local_datasets(client=None)

        self.assertFalse(result["enabled"])
        self.assertEqual(result["datasets"], [])
        self.assertIn("not configured", result["reason"])

    def test_syncs_core_and_retrieval_datasets(self) -> None:
        fake_settings = types.SimpleNamespace(
            langsmith_api_key="test-key",
            langsmith_endpoint="https://example.test",
            langsmith_project="mini-openclaw-evals",
        )
        client = _FakeClient()
        with patch.object(sync_mod, "get_settings", return_value=fake_settings):
            result = sync_mod.sync_local_datasets(
                client=client,
                tasks_path=Path("backend/evals/datasets/core_tasks.json"),
                retrieval_path=Path("backend/evals/datasets/retrieval_quality.json"),
            )

        self.assertTrue(result["enabled"])
        self.assertEqual(result["project_name"], "mini-openclaw-evals")
        self.assertEqual(len(result["datasets"]), 2)
        statuses = {row["name"]: row["status"] for row in result["datasets"]}
        self.assertEqual(
            statuses[sync_mod.CORE_LANGSMITH_DATASET_NAME],
            "created",
        )
        self.assertEqual(
            statuses[sync_mod.RETRIEVAL_LANGSMITH_DATASET_NAME],
            "created",
        )
        self.assertEqual(len(client.created), 2)
        self.assertEqual(len(client.created_examples), 2)
        self.assertGreater(result["datasets"][0]["example_count"], 0)

    def test_existing_datasets_are_left_alone(self) -> None:
        fake_settings = types.SimpleNamespace(
            langsmith_api_key="test-key",
            langsmith_endpoint="https://example.test",
            langsmith_project="mini-openclaw-evals",
        )
        client = _FakeClient(
            existing={
                sync_mod.CORE_LANGSMITH_DATASET_NAME: _FakeDataset("core-id", 25),
                sync_mod.RETRIEVAL_LANGSMITH_DATASET_NAME: _FakeDataset(
                    "retrieval-id",
                    5,
                ),
            }
        )
        with patch.object(sync_mod, "get_settings", return_value=fake_settings):
            result = sync_mod.sync_local_datasets(client=client)

        self.assertEqual(len(result["datasets"]), 2)
        self.assertEqual(client.created, [])
        self.assertEqual(client.created_examples, [])
        self.assertEqual(result["datasets"][0]["status"], "existing")
        self.assertEqual(result["datasets"][1]["status"], "existing")


if __name__ == "__main__":
    unittest.main()
