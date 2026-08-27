from __future__ import annotations

import unittest

from backend.evals.live_graph_retrieval import LiveRetrievalCase, run_live_evaluation


class LiveGraphRetrievalTests(unittest.TestCase):
    def test_live_evaluation_uses_graph_expansion_not_fixture_rankings(self) -> None:
        graph = {
            "nodes": [
                {"id": "doc:direct", "type": "document", "label": "retrieval.md", "path": "knowledge/retrieval.md", "metadata": {}, "summary": "retrieval"},
                {"id": "doc:expanded", "type": "document", "label": "evidence.md", "path": "workspace/evidence.md", "metadata": {}, "summary": "supporting evidence"},
            ],
            "edges": [{"id": "edge:1", "source": "doc:direct", "target": "doc:expanded", "type": "references", "metadata": {}}],
        }
        report = run_live_evaluation(
            [LiveRetrievalCase("case-1", "retrieval", ["knowledge/retrieval.md", "workspace/evidence.md"])],
            graph=graph,
        )

        self.assertEqual(report["execution_mode"], "live_graph_index")
        self.assertEqual(report["summary"]["direct_graph_match"]["recall_at_k"], 0.5)
        self.assertEqual(report["summary"]["graph_assisted"]["recall_at_k"], 1.0)


if __name__ == "__main__":
    unittest.main()
