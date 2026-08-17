from __future__ import annotations

import unittest

from backend.evals.strict_hybrid_graph_retrieval import Candidate, _dedupe_and_rank


class StrictHybridGraphRetrievalTests(unittest.TestCase):
    def test_reranker_deduplicates_sources_and_prefers_query_relevant_candidate(self) -> None:
        ranked = _dedupe_and_rank(
            "graph evidence retrieval",
            [
                Candidate("docs/a.md", "graph evidence", origins=("hybrid",)),
                Candidate("docs/a.md", "graph evidence", origins=("graph_direct",)),
                Candidate("docs/b.md", "unrelated notes", origins=("graph_expanded",), hop=1, edge_type="mentions"),
                Candidate("docs/c.md", "retrieval graph evidence", origins=("graph_expanded",), hop=1, edge_type="references"),
            ],
            top_k=5,
        )

        self.assertEqual([candidate.path for candidate in ranked], ["docs/c.md", "docs/a.md", "docs/b.md"])
        self.assertEqual(ranked[1].origins, ("graph_direct", "hybrid"))


if __name__ == "__main__":
    unittest.main()
