"""Run a live, path-labeled comparison for graph-assisted evidence discovery."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean
from typing import Any

from backend.evals.runner import compute_retrieval_metrics
from backend.graph.index import build_graph, expand_graph_evidence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET_PATH = PROJECT_ROOT / "backend" / "evals" / "datasets" / "live_graph_retrieval.json"
SOURCE_NODE_TYPES = {"document", "workspace_file", "skill", "trace", "heading"}


@dataclass(frozen=True)
class LiveRetrievalCase:
    id: str
    query: str
    relevant_paths: list[str]


def load_cases(path: str | Path = DEFAULT_DATASET_PATH) -> list[LiveRetrievalCase]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("live retrieval dataset must be a JSON array")
    return [
        LiveRetrievalCase(
            id=str(item["id"]),
            query=str(item["query"]),
            relevant_paths=[str(value) for value in item["relevant_paths"]],
        )
        for item in raw
    ]


def _source_paths(node_ids: list[str], nodes_by_id: dict[str, dict[str, Any]]) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for node_id in node_ids:
        node = nodes_by_id.get(node_id, {})
        path = node.get("path")
        if (
            node.get("type") not in SOURCE_NODE_TYPES
            or not isinstance(path, str)
            or not path
            or path in seen
        ):
            continue
        seen.add(path)
        paths.append(path)
    return paths


def _summary(rows: list[dict[str, Any]], strategy: str) -> dict[str, float | int]:
    metric_names = ("recall_at_k", "mrr", "hit_at_1", "ndcg_at_k")
    selected = [row for row in rows if row["strategy"] == strategy]
    return {
        "case_count": len(selected),
        **{
            name: round(fmean(float(row["metrics"][name]) for row in selected), 4)
            if selected else 0.0
            for name in metric_names
        },
    }


def run_live_evaluation(
    cases: list[LiveRetrievalCase], *, top_k: int = 5, graph: dict[str, Any] | None = None
) -> dict[str, Any]:
    active_graph = graph or build_graph()
    nodes_by_id = {str(node["id"]): node for node in active_graph.get("nodes", [])}
    rows: list[dict[str, Any]] = []
    for case in cases:
        expanded = expand_graph_evidence(
            case.query,
            graph=active_graph,
            max_hops=2,
            max_nodes=8,
        )
        direct_paths = _source_paths(expanded["direct_node_ids"], nodes_by_id)
        graph_paths = _source_paths(
            [str(node["id"]) for node in expanded["evidence"]],
            nodes_by_id,
        )
        for strategy, retrieved_paths in (
            ("direct_graph_match", direct_paths),
            ("graph_assisted", graph_paths),
        ):
            rows.append(
                {
                    "case_id": case.id,
                    "query": case.query,
                    "strategy": strategy,
                    "relevant_paths": case.relevant_paths,
                    "retrieved_paths": retrieved_paths[:top_k],
                    "metrics": compute_retrieval_metrics(
                        retrieved_paths, case.relevant_paths, top_k=top_k
                    ),
                }
            )

    direct = _summary(rows, "direct_graph_match")
    assisted = _summary(rows, "graph_assisted")
    return {
        "execution_mode": "live_graph_index",
        "top_k": top_k,
        "case_count": len(cases),
        "graph_node_count": len(active_graph.get("nodes", [])),
        "graph_edge_count": len(active_graph.get("edges", [])),
        "summary": {"direct_graph_match": direct, "graph_assisted": assisted},
        "delta_vs_direct": {
            name: round(float(assisted[name]) - float(direct[name]), 4)
            for name in ("recall_at_k", "mrr", "hit_at_1", "ndcg_at_k")
        },
        "cases": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run live graph retrieval evaluation")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET_PATH))
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    report = run_live_evaluation(load_cases(args.dataset), top_k=args.top_k)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
