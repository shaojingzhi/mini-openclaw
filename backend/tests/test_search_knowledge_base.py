"""Unit tests for the search_knowledge_base agent tool (US-008)."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import importlib

from backend.tools.search_knowledge_base import (
    EMPTY_KB_MESSAGE,
    clear_cache,
    search_knowledge_base,
)

# Reach the module via sys.modules — `backend.tools` re-exports the
# `search_knowledge_base` tool object under the same name, which would
# shadow the module if we tried ``from backend.tools import …`` here.
sk_mod = importlib.import_module("backend.tools.search_knowledge_base")


class SearchKnowledgeBaseEmptyTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = Path(tempfile.mkdtemp(prefix="kb-empty-"))
        (self._tmp / "knowledge").mkdir()
        clear_cache()
        self._k = patch.object(sk_mod, "KNOWLEDGE_DIR", self._tmp / "knowledge")
        self._s = patch.object(sk_mod, "STORAGE_DIR", self._tmp / "storage")
        self._k.start()
        self._s.start()

    def tearDown(self) -> None:
        clear_cache()
        self._k.stop()
        self._s.stop()
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_empty_knowledge_dir_returns_clear_message(self) -> None:
        out = search_knowledge_base.invoke({"query": "anything"})
        self.assertEqual(out, EMPTY_KB_MESSAGE)

    def test_missing_knowledge_dir_returns_clear_message(self) -> None:
        # Drop the empty directory entirely so the existence check fires.
        shutil.rmtree(self._tmp / "knowledge")
        out = search_knowledge_base.invoke({"query": "anything"})
        self.assertEqual(out, EMPTY_KB_MESSAGE)


class SearchKnowledgeBaseSeededTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = Path(tempfile.mkdtemp(prefix="kb-seeded-"))
        knowledge = self._tmp / "knowledge"
        knowledge.mkdir()
        (knowledge / "notes.md").write_text(
            "# Marshmallow Recipe\n\n"
            "To make fluffy marshmallows you need gelatin and corn syrup.\n"
            "Whip the mixture for ten minutes until stiff peaks form.\n",
            encoding="utf-8",
        )
        clear_cache()
        self._k = patch.object(sk_mod, "KNOWLEDGE_DIR", knowledge)
        self._s = patch.object(sk_mod, "STORAGE_DIR", self._tmp / "storage")
        self._k.start()
        self._s.start()

    def tearDown(self) -> None:
        clear_cache()
        self._k.stop()
        self._s.stop()
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_keyword_retrieves_seeded_document(self) -> None:
        out = search_knowledge_base.invoke({"query": "marshmallow"})
        # Source filename appears in the header.
        self.assertIn("notes.md", out)
        # Document body content was returned.
        self.assertIn("Marshmallow Recipe", out)

    def test_persists_index_to_storage_dir(self) -> None:
        # First call triggers the build + persist path.
        search_knowledge_base.invoke({"query": "marshmallow"})
        storage = self._tmp / "storage"
        self.assertTrue((storage / "docstore.json").is_file())

        # Second call (after dropping the cache) should reload from
        # persisted storage rather than rebuild — observable by the fact
        # that no further crash occurs even though the documents on
        # disk are still readable; we just assert the result is
        # non-empty and still mentions our file.
        clear_cache()
        out = search_knowledge_base.invoke({"query": "marshmallow"})
        self.assertIn("notes.md", out)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
