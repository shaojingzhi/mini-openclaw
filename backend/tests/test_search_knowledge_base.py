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
    GRAPH_UNAVAILABLE_MESSAGE,
    NO_RESULTS_MESSAGE,
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
        nested = knowledge / "interview"
        nested.mkdir()
        (nested / "graph_notes.md").write_text(
            "# Graph Retrieval Notes\n\n"
            "Graph expansion should rerank evidence before it reaches the prompt.\n",
            encoding="utf-8",
        )
        clear_cache()
        self._k = patch.object(sk_mod, "KNOWLEDGE_DIR", knowledge)
        self._s = patch.object(sk_mod, "STORAGE_DIR", self._tmp / "storage")
        self._graph = patch.object(
            sk_mod,
            "expand_graph_evidence",
            return_value={
                "available": True,
                "direct_node_ids": ["document:direct"],
                "expanded_node_ids": ["skill:expanded", "concept:structure"],
                "edge_types": ["mentions", "uses_tool"],
                "evidence": [
                    {
                        "id": "document:direct",
                        "type": "document",
                        "label": "notes.md",
                        "path": "backend/knowledge/notes.md",
                        "metadata": {},
                    },
                    {
                        "id": "skill:expanded",
                        "type": "skill",
                        "label": "resume_story_coach",
                        "path": "backend/skills/resume_story_coach/SKILL.md",
                        "summary": "The skill turns validated project evidence into a concise interview story.",
                        "metadata": {},
                    },
                    {
                        "id": "concept:structure",
                        "type": "concept",
                        "label": "interview",
                        "metadata": {},
                    },
                ],
                "expansion_paths": {
                    "skill:expanded": {"from_node_id": "document:direct", "from_title": "notes.md", "edge_type": "uses_tool"},
                    "concept:structure": {"from_node_id": "document:direct", "from_title": "notes.md", "edge_type": "mentions"},
                },
            },
        )
        self._k.start()
        self._s.start()
        self._graph.start()

    def tearDown(self) -> None:
        clear_cache()
        self._graph.stop()
        self._k.stop()
        self._s.stop()
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_keyword_retrieves_seeded_document(self) -> None:
        out = search_knowledge_base.invoke({"query": "marshmallow"})
        # Source filename appears in the header.
        self.assertIn("notes.md", out)
        # Document body content was returned.
        self.assertIn("Marshmallow Recipe", out)
        self.assertNotIn("Graph-expanded evidence", out)

    def test_keyword_retrieves_nested_document(self) -> None:
        out = search_knowledge_base.invoke({"query": "rerank evidence"})
        self.assertIn("graph_notes.md", out)
        self.assertIn("Graph Retrieval Notes", out)

    def test_graph_mode_appends_related_evidence(self) -> None:
        out = search_knowledge_base.invoke(
            {"query": "marshmallow", "use_graph": True}
        )
        self.assertIn("Direct matches:", out)
        self.assertIn("Marshmallow Recipe", out)
        self.assertIn("Graph-expanded evidence:", out)
        self.assertIn("resume_story_coach", out)
        self.assertIn("The skill turns validated project evidence", out)
        self.assertIn("from notes.md via uses_tool", out)
        self.assertIn("结构线索", out)
        self.assertIn("Traversed edge types: mentions, uses_tool", out)

    def test_graph_mode_reports_missing_graph(self) -> None:
        self._graph.stop()
        self._graph = patch.object(
            sk_mod,
            "expand_graph_evidence",
            return_value={
                "available": False,
                "direct_node_ids": [],
                "expanded_node_ids": [],
                "edge_types": [],
                "evidence": [],
            },
        )
        self._graph.start()

        out = search_knowledge_base.invoke(
            {"query": "marshmallow", "use_graph": True}
        )

        self.assertIn(GRAPH_UNAVAILABLE_MESSAGE, out)

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

    def test_empty_retrieval_results_return_clear_message(self) -> None:
        class _NoResultsRetriever:
            def retrieve(self, query: str):
                return []

        with patch.object(sk_mod, "_get_retriever", return_value=_NoResultsRetriever()):
            out = search_knowledge_base.invoke({"query": "unknown topic"})

        self.assertEqual(out, NO_RESULTS_MESSAGE)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
