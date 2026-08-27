"""Compare hybrid retrieval with hybrid retrieval augmented by graph candidates.

Both strategies are constrained to the same final source-artifact budget. The
reranker is intentionally deterministic and lexical so this evaluation remains
local and reproducible without an LLM judge or external reranking service.
"""

from __future__ import annotations

import argparse
import json
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from statistics import fmean
from typing import Any, Iterable

from backend.evals.live_graph_retrieval import LiveRetrievalCase, load_cases
from backend.evals.runner import compute_retrieval_metrics
from backend.graph.index import build_graph, expand_graph_evidence
from backend.tools.search_knowledge_base import KNOWLEDGE_DIR, _build_hybrid_retriever

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_NODE_TYPES = {"document", "workspace_file", "skill", "trace"}
TERM_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")
STOP_WORDS = {"and", "for", "from", "how", "the", "this", "what", "which", "with"}
EDGE_BONUS = {"references": 0.12, "uses_tool": 0.10, "failed_at": 0.08, "contains": 0.06, "mentions": 0.03}


@dataclass(frozen=True)
class Candidate:
    path: str
    text: str
    origins: tuple[str, ...] = field(default_factory=tuple)
    hop: int = 0
    edge_type: str | None = None
    score: float = 0.0


def _relative_path(raw_path: str) -> str:
    path = Path(raw_path).resolve()
    try:
        return path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _query_terms(query: str) -> set[str]:
    return {
        match.group(0).lower()
        for match in TERM_PATTERN.finditer(query)
        if match.group(0).lower() not in STOP_WORDS
    }


def _lexical_score(query: str, text: str) -> float:
    terms = _query_terms(query)
    if not terms:
        return 0.0
    haystack = text.lower()
    return sum(term in haystack for term in terms) / len(terms)


def _score_candidate(query: str, candidate: Candidate) -> float:
    lexical = _lexical_score(query, f"{candidate.path}\n{candidate.text}")
    origin_bonus = 0.12 if "hybrid" in candidate.origins else 0.06
    edge_bonus = EDGE_BONUS.get(candidate.edge_type or "", 0.0)
    hop_penalty = 0.04 * candidate.hop
    return round(lexical + origin_bonus + edge_bonus - hop_penalty, 6)


def _dedupe_and_rank(query: str, candidates: Iterable[Candidate], *, top_k: int) -> list[Candidate]:
    merged: dict[str, Candidate] = {}
    for candidate in candidates:
        scored = Candidate(
            path=candidate.path,
            text=candidate.text,
            origins=candidate.origins,
            hop=candidate.hop,
            edge_type=candidate.edge_type,
            score=_score_candidate(query, candidate),
        )
        existing = merged.get(scored.path)
        origins = tuple(
            sorted(set(existing.origins if existing else ()) | set(scored.origins))
        )
        if existing is None or scored.score > existing.score:
            merged[scored.path] = Candidate(
                path=scored.path,
                text=scored.text,
                origins=origins,
                hop=min(existing.hop, scored.hop) if existing else scored.hop,
                edge_type=scored.edge_type or (existing.edge_type if existing else None),
                score=scored.score,
            )
        else:
            merged[scored.path] = Candidate(
                path=existing.path,
                text=existing.text,
                origins=tuple(sorted(set(existing.origins) | set(scored.origins))),
                hop=min(existing.hop, scored.hop),
                edge_type=existing.edge_type or scored.edge_type,
                score=existing.score,
            )
    return sorted(merged.values(), key=lambda item: (-item.score, item.path))[:top_k]


def _hybrid_candidates(query: str, retriever: Any | None) -> list[Candidate]:
    if retriever is None:
        return []
    candidates: list[Candidate] = []
    for node in retriever.retrieve(query):
        metadata = getattr(node, "metadata", {}) or {}
        source = metadata.get("file_path") or metadata.get("file_name")
        if not isinstance(source, str) or not source:
            continue
        candidates.append(
            Candidate(
                path=_relative_path(source),
                text=node.get_content(),
                origins=("hybrid",),
            )
        )
    return candidates


def _graph_candidates(
    query: str, graph: dict[str, Any], *, include_expanded: bool = True
) -> list[Candidate]:
    result = expand_graph_evidence(query, graph=graph, max_hops=2, max_nodes=8)
    nodes_by_id = {str(node["id"]): node for node in graph.get("nodes", [])}
    candidates: list[Candidate] = []
    node_ids = list(result["direct_node_ids"])
    if include_expanded:
        node_ids.extend(result["expanded_node_ids"])
    for node_id in node_ids:
        node = nodes_by_id.get(node_id, {})
        path = node.get("path")
        if node.get("type") not in SOURCE_NODE_TYPES or not isinstance(path, str):
            continue
        relation = result.get("expansion_paths", {}).get(node_id, {})
        is_expanded = include_expanded and node_id in result["expanded_node_ids"]
        candidates.append(
            Candidate(
                path=path,
                text=str(node.get("summary", "")),
                origins=("graph_expanded" if is_expanded else "graph_direct",),
                hop=1 if is_expanded else 0,
                edge_type=str(relation.get("edge_type")) if is_expanded else None,
            )
        )
    return candidates


def _summary(rows: list[dict[str, Any]], strategy: str) -> dict[str, float | int]:
    selected = [row for row in rows if row["strategy"] == strategy]
    metrics = ("recall_at_k", "mrr", "hit_at_1", "ndcg_at_k")
    return {
        "case_count": len(selected),
        **{
            metric: round(fmean(float(row["metrics"][metric]) for row in selected), 4)
            if selected else 0.0
            for metric in metrics
        },
    }


def run_strict_evaluation(
    cases: list[LiveRetrievalCase], *, top_k: int = 5, graph: dict[str, Any] | None = None
) -> dict[str, Any]:
    active_graph = graph or build_graph()
    rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="mini-openclaw-strict-eval-") as storage_dir:
        retriever = _build_hybrid_retriever(KNOWLEDGE_DIR, Path(storage_dir))
        for case in cases:
            hybrid = _hybrid_candidates(case.query, retriever)
            baseline = _dedupe_and_rank(case.query, hybrid, top_k=top_k)
            graph_direct = _dedupe_and_rank(
                case.query,
                [*hybrid, *_graph_candidates(case.query, active_graph, include_expanded=False)],
                top_k=top_k,
            )
            augmented = _dedupe_and_rank(
                case.query,
                [*hybrid, *_graph_candidates(case.query, active_graph)],
                top_k=top_k,
            )
            for strategy, candidates in (
                ("hybrid_only", baseline),
                ("hybrid_plus_graph_direct_reranked", graph_direct),
                ("hybrid_plus_graph_bfs_reranked", augmented),
            ):
                paths = [candidate.path for candidate in candidates]
                rows.append(
                    {
                        "case_id": case.id,
                        "query": case.query,
                        "strategy": strategy,
                        "relevant_paths": case.relevant_paths,
                        "retrieved_paths": paths,
                        "candidates": [
                            {
                                "path": candidate.path,
                                "origins": list(candidate.origins),
                                "hop": candidate.hop,
                                "edge_type": candidate.edge_type,
                                "rerank_score": candidate.score,
                            }
                            for candidate in candidates
                        ],
                        "metrics": compute_retrieval_metrics(paths, case.relevant_paths, top_k=top_k),
                    }
                )

    baseline_summary = _summary(rows, "hybrid_only")
    direct_summary = _summary(rows, "hybrid_plus_graph_direct_reranked")
    augmented_summary = _summary(rows, "hybrid_plus_graph_bfs_reranked")
    metric_names = ("recall_at_k", "mrr", "hit_at_1", "ndcg_at_k")
    return {
        "execution_mode": "live_hybrid_graph_lexical_rerank",
        "top_k": top_k,
        "case_count": len(cases),
        "graph_node_count": len(active_graph.get("nodes", [])),
        "graph_edge_count": len(active_graph.get("edges", [])),
        "rerank_policy": {
            "lexical_term_overlap": True,
            "hybrid_origin_bonus": 0.12,
            "graph_origin_bonus": 0.06,
            "edge_bonus": EDGE_BONUS,
            "hop_penalty_per_hop": 0.04,
        },
        "summary": {
            "hybrid_only": baseline_summary,
            "hybrid_plus_graph_direct_reranked": direct_summary,
            "hybrid_plus_graph_bfs_reranked": augmented_summary,
        },
        "delta_vs_hybrid": {
            metric: round(float(augmented_summary[metric]) - float(baseline_summary[metric]), 4)
            for metric in metric_names
        },
        "bfs_delta_vs_graph_direct": {
            metric: round(float(augmented_summary[metric]) - float(direct_summary[metric]), 4)
            for metric in metric_names
        },
        "cases": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run strict hybrid plus graph retrieval evaluation")
    parser.add_argument("--dataset", default=None)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    cases = load_cases(args.dataset) if args.dataset else load_cases()
    report = run_strict_evaluation(cases, top_k=args.top_k)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
