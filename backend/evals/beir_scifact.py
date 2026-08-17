"""Run the existing hybrid retriever against the public BEIR SciFact corpus."""

from __future__ import annotations

import argparse
import csv
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean
from typing import Any

from backend.evals.runner import compute_retrieval_metrics
from backend.tools.search_knowledge_base import _build_hybrid_retriever

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET_DIR = PROJECT_ROOT / "backend" / "evals" / "benchmarks" / "scifact"


@dataclass(frozen=True)
class SciFactQuery:
    query_id: str
    text: str
    relevant_document_ids: list[str]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def load_scifact_queries(dataset_dir: str | Path, *, limit: int | None = 100) -> list[SciFactQuery]:
    root = Path(dataset_dir)
    queries = {
        str(item["_id"]): str(item["text"])
        for item in _read_jsonl(root / "queries.jsonl")
    }
    relevant: dict[str, list[str]] = {}
    with (root / "qrels" / "test.tsv").open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if int(row["score"]) > 0:
                relevant.setdefault(str(row["query-id"]), []).append(str(row["corpus-id"]))

    query_ids = sorted(relevant, key=lambda value: int(value) if value.isdigit() else value)
    if limit is not None:
        query_ids = query_ids[:limit]
    return [
        SciFactQuery(query_id, queries[query_id], sorted(set(relevant[query_id])))
        for query_id in query_ids
        if query_id in queries
    ]


def _materialize_corpus(dataset_dir: Path, target_dir: Path) -> None:
    for item in _read_jsonl(dataset_dir / "corpus.jsonl"):
        document_id = str(item["_id"])
        title = str(item.get("title") or "")
        text = str(item.get("text") or "")
        (target_dir / f"{document_id}.md").write_text(
            f"# {title}\n\n{text}\n", encoding="utf-8"
        )


def _retrieved_document_ids(retriever: Any, query: str) -> list[str]:
    document_ids: list[str] = []
    seen: set[str] = set()
    for node in retriever.retrieve(query):
        metadata = getattr(node, "metadata", {}) or {}
        filename = metadata.get("file_name") or Path(str(metadata.get("file_path", ""))).name
        document_id = Path(str(filename)).stem
        if document_id and document_id not in seen:
            seen.add(document_id)
            document_ids.append(document_id)
    return document_ids


def run_scifact_evaluation(
    dataset_dir: str | Path, *, query_limit: int = 100, top_k: int = 5
) -> dict[str, Any]:
    root = Path(dataset_dir)
    if not (root / "corpus.jsonl").is_file():
        raise FileNotFoundError(
            f"SciFact corpus not found at {root}. Run scripts/download_beir_scifact.sh first."
        )
    queries = load_scifact_queries(root, limit=query_limit)
    rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="mini-openclaw-scifact-corpus-") as corpus_dir, tempfile.TemporaryDirectory(prefix="mini-openclaw-scifact-index-") as storage_dir:
        _materialize_corpus(root, Path(corpus_dir))
        retriever = _build_hybrid_retriever(Path(corpus_dir), Path(storage_dir))
        if retriever is None:
            raise RuntimeError("SciFact corpus materialized without readable documents")
        for query in queries:
            retrieved = _retrieved_document_ids(retriever, query.text)
            rows.append(
                {
                    "query_id": query.query_id,
                    "query": query.text,
                    "relevant_document_ids": query.relevant_document_ids,
                    "retrieved_document_ids": retrieved[:top_k],
                    "metrics": compute_retrieval_metrics(
                        retrieved, query.relevant_document_ids, top_k=top_k
                    ),
                }
            )

    metric_names = ("recall_at_k", "mrr", "hit_at_1", "ndcg_at_k")
    return {
        "execution_mode": "live_beir_scifact_hybrid_retrieval",
        "dataset": "BEIR SciFact",
        "split": "test",
        "retrieval_mode": (
            "hybrid_bm25_vector" if os.getenv("OPENAI_API_KEY") else "bm25_fallback"
        ),
        "query_count": len(rows),
        "top_k": top_k,
        "metrics": {
            metric: round(fmean(float(row["metrics"][metric]) for row in rows), 4)
            if rows else 0.0
            for metric in metric_names
        },
        "queries": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate hybrid retrieval on BEIR SciFact")
    parser.add_argument("--dataset-dir", default=str(DEFAULT_DATASET_DIR))
    parser.add_argument("--query-limit", type=int, default=100)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    report = run_scifact_evaluation(
        args.dataset_dir, query_limit=args.query_limit, top_k=args.top_k
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["metrics"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
