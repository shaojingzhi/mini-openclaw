from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.evals.hotpotqa_title_graph import (
    Passage,
    build_title_mention_graph,
    load_hotpotqa_questions,
    select_bfs_fixed,
)


class HotpotQATitleGraphTests(unittest.TestCase):
    def test_loader_reads_hugging_face_rows_and_deduplicates_support_titles(self) -> None:
        payload = {
            "rows": [
                {
                    "row": {
                        "id": "sample-1",
                        "question": "Which article connects Alpha and Beta?",
                        "supporting_facts": {"title": ["Alpha", "Beta", "Alpha"]},
                        "context": {
                            "title": [f"Doc {index}" for index in range(8)] + ["Alpha", "Beta"],
                            "sentences": [["text"] for _ in range(10)],
                        },
                    }
                }
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hotpot.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            questions = load_hotpotqa_questions(path)

        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0].supporting_titles, ("Alpha", "Beta"))
        self.assertEqual(len(questions[0].passages), 10)

    def test_title_graph_uses_visible_bodies_not_gold_labels(self) -> None:
        passages = (
            Passage("Alpha", "Alpha does not name the other passage."),
            Passage("Beta Topic", "The Alpha project is relevant here."),
            Passage("Gamma", "unrelated"),
        )
        graph = build_title_mention_graph(passages)

        self.assertEqual(graph["Alpha"], ["Beta Topic"])
        self.assertEqual(graph["Beta Topic"], ["Alpha"])
        self.assertEqual(graph["Gamma"], [])

    def test_fixed_bfs_places_reachable_passage_before_bm25_fill(self) -> None:
        scores = {"Seed": 10.0, "Bridge": 3.0, "Other": 8.0, "Tail": 1.0}
        graph = {"Seed": ["Bridge"], "Bridge": ["Seed", "Tail"], "Other": [], "Tail": ["Bridge"]}

        selected = select_bfs_fixed(scores, graph, top_k=4, seed_count=1, max_hops=2)

        self.assertEqual([item.title for item in selected], ["Seed", "Bridge", "Tail", "Other"])
        self.assertEqual([item.hop for item in selected], [0, 1, 2, None])


if __name__ == "__main__":
    unittest.main()
