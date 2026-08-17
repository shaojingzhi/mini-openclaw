from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.evals.beir_scifact import load_scifact_queries


class SciFactLoaderTests(unittest.TestCase):
    def test_loads_only_test_queries_with_positive_qrels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "qrels").mkdir()
            (root / "queries.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps({"_id": "2", "text": "second"}),
                        json.dumps({"_id": "1", "text": "first"}),
                    ]
                ) + "\n",
                encoding="utf-8",
            )
            (root / "qrels" / "test.tsv").write_text(
                "query-id\tcorpus-id\tscore\n1\tdoc-a\t1\n1\tdoc-b\t0\n2\tdoc-c\t1\n",
                encoding="utf-8",
            )

            queries = load_scifact_queries(root, limit=1)

        self.assertEqual(
            [(query.query_id, query.relevant_document_ids) for query in queries],
            [("1", ["doc-a"])],
        )


if __name__ == "__main__":
    unittest.main()
