"""Evaluate title-mention BFS against BM25 on HotpotQA distractor passages.

The graph is derived only from each question's ten visible candidate passages.
Gold supporting-fact titles are retained exclusively for metric calculation.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, deque
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean
from typing import Any, Iterable

from backend.evals.runner import compute_retrieval_metrics

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET_PATH = (
    PROJECT_ROOT
    / "backend"
    / "evals"
    / "benchmarks"
    / "hotpotqa_distractor"
    / "validation_offset_0_length_100.json"
)
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")
MIN_TITLE_ALNUM_LENGTH = 4
EDGE_BONUS = 0.03
HOP_PENALTY = 0.02


@dataclass(frozen=True)
class Passage:
    title: str
    text: str


@dataclass(frozen=True)
class HotpotQuestion:
    question_id: str
    question: str
    supporting_titles: tuple[str, ...]
    passages: tuple[Passage, ...]


@dataclass(frozen=True)
class RankedPassage:
    title: str
    bm25_score: float
    rank_score: float
    origin: str
    hop: int | None = None


def _tokens(text: str) -> list[str]:
    return [match.group(0).lower() for match in TOKEN_PATTERN.finditer(text)]


def _title_key(title: str) -> str:
    return " ".join(_tokens(title))


def _parse_context(raw_context: Any) -> tuple[Passage, ...]:
    if isinstance(raw_context, dict):
        titles = raw_context.get("title", [])
        sentence_lists = raw_context.get("sentences", [])
        pairs: Iterable[tuple[Any, Any]] = zip(titles, sentence_lists)
    elif isinstance(raw_context, list):
        pairs = (
            (item[0], item[1])
            for item in raw_context
            if isinstance(item, list) and len(item) == 2
        )
    else:
        return ()
    return tuple(
        Passage(str(title), " ".join(str(sentence) for sentence in sentences))
        for title, sentences in pairs
        if isinstance(sentences, list) and str(title).strip()
    )


def _supporting_titles(raw_supporting_facts: Any) -> tuple[str, ...]:
    if isinstance(raw_supporting_facts, dict):
        titles = raw_supporting_facts.get("title", [])
    elif isinstance(raw_supporting_facts, list):
        titles = [item[0] for item in raw_supporting_facts if isinstance(item, list) and item]
    else:
        titles = []
    return tuple(dict.fromkeys(str(title) for title in titles if str(title).strip()))


def load_hotpotqa_questions(path: str | Path, *, limit: int | None = 100) -> list[HotpotQuestion]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = raw.get("rows", raw) if isinstance(raw, dict) else raw
    if not isinstance(rows, list):
        raise ValueError("HotpotQA data must be a list or a Hugging Face rows response")

    questions: list[HotpotQuestion] = []
    for item in rows:
        row = item.get("row", item) if isinstance(item, dict) else None
        if not isinstance(row, dict):
            continue
        passages = _parse_context(row.get("context"))
        supporting_titles = _supporting_titles(row.get("supporting_facts"))
        if len(passages) != 10 or len(supporting_titles) < 2:
            continue
        questions.append(
            HotpotQuestion(
                question_id=str(row["id"]),
                question=str(row["question"]),
                supporting_titles=supporting_titles,
                passages=passages,
            )
        )
        if limit is not None and len(questions) >= limit:
            break
    return questions


def bm25_scores(query: str, passages: tuple[Passage, ...]) -> dict[str, float]:
    """Score each candidate passage using a dependency-free BM25 implementation."""
    documents = {passage.title: _tokens(f"{passage.title} {passage.text}") for passage in passages}
    term_frequencies = {title: Counter(tokens) for title, tokens in documents.items()}
    document_frequency = Counter(
        term for tokens in documents.values() for term in set(tokens)
    )
    average_length = fmean(len(tokens) for tokens in documents.values()) if documents else 0.0
    query_terms = _tokens(query)
    scores: dict[str, float] = {}
    for title, frequencies in term_frequencies.items():
        score = 0.0
        document_length = len(documents[title])
        for term in query_terms:
            frequency = frequencies.get(term, 0)
            if not frequency:
                continue
            inverse_frequency = math.log(
                1 + (len(documents) - document_frequency[term] + 0.5) / (document_frequency[term] + 0.5)
            )
            denominator = frequency + 1.2 * (1 - 0.75 + 0.75 * document_length / average_length)
            score += inverse_frequency * frequency * 2.2 / denominator
        scores[title] = score
    return scores


def build_title_mention_graph(passages: tuple[Passage, ...]) -> dict[str, list[str]]:
    """Link passages when a body explicitly names another visible candidate title.

    Supporting facts are intentionally not accepted by this function. Graph
    construction can therefore use only retrieval-time-visible context.
    """
    adjacency: dict[str, set[str]] = {passage.title: set() for passage in passages}
    title_keys = {passage.title: _title_key(passage.title) for passage in passages}
    for source in passages:
        body = _title_key(source.text)
        for target in passages:
            if source.title == target.title:
                continue
            target_key = title_keys[target.title]
            if len("".join(target_key.split())) < MIN_TITLE_ALNUM_LENGTH:
                continue
            if target_key in body:
                adjacency[source.title].add(target.title)
                adjacency[target.title].add(source.title)
    return {title: sorted(neighbors) for title, neighbors in adjacency.items()}


def _bm25_order(scores: dict[str, float]) -> list[str]:
    return sorted(scores, key=lambda title: (-scores[title], title))


def _bfs_hops(
    seeds: list[str], graph: dict[str, list[str]], scores: dict[str, float], *, max_hops: int
) -> dict[str, int]:
    hops = {title: 0 for title in seeds}
    queue: deque[str] = deque(seeds)
    while queue:
        current = queue.popleft()
        if hops[current] >= max_hops:
            continue
        for neighbor in sorted(graph.get(current, []), key=lambda title: (-scores[title], title)):
            if neighbor in hops:
                continue
            hops[neighbor] = hops[current] + 1
            queue.append(neighbor)
    return hops


def select_bm25_only(scores: dict[str, float], *, top_k: int) -> list[RankedPassage]:
    return [
        RankedPassage(title, scores[title], scores[title], "bm25")
        for title in _bm25_order(scores)[:top_k]
    ]


def select_bfs_fixed(
    scores: dict[str, float], graph: dict[str, list[str]], *, top_k: int, seed_count: int = 2, max_hops: int = 2
) -> list[RankedPassage]:
    order = _bm25_order(scores)
    hops = _bfs_hops(order[:seed_count], graph, scores, max_hops=max_hops)
    bfs_order = sorted(hops, key=lambda title: (hops[title], -scores[title], title))
    selected: list[str] = []
    for title in [*bfs_order, *order]:
        if title not in selected:
            selected.append(title)
        if len(selected) >= top_k:
            break
    return [
        RankedPassage(
            title,
            scores[title],
            scores[title],
            "bm25_seed" if hops.get(title) == 0 else "title_bfs" if title in hops else "bm25_fill",
            hops.get(title),
        )
        for title in selected
    ]


def select_bfs_reranked(
    scores: dict[str, float], graph: dict[str, list[str]], *, top_k: int, seed_count: int = 2, max_hops: int = 2
) -> list[RankedPassage]:
    order = _bm25_order(scores)
    hops = _bfs_hops(order[:seed_count], graph, scores, max_hops=max_hops)
    pool = dict.fromkeys([*order[:top_k], *hops])
    max_bm25 = max(scores.values(), default=0.0)
    ranked: list[RankedPassage] = []
    for title in pool:
        hop = hops.get(title)
        edge_adjustment = EDGE_BONUS - HOP_PENALTY * hop if hop and hop > 0 else 0.0
        normalized_bm25 = scores[title] / max_bm25 if max_bm25 else 0.0
        ranked.append(
            RankedPassage(
                title,
                scores[title],
                normalized_bm25 + edge_adjustment,
                "title_bfs" if hop and hop > 0 else "bm25",
                hop,
            )
        )
    return sorted(ranked, key=lambda item: (-item.rank_score, -item.bm25_score, item.title))[:top_k]


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


def run_hotpotqa_evaluation(
    questions: list[HotpotQuestion], *, top_k: int = 5, seed_count: int = 2, max_hops: int = 2
) -> dict[str, Any]:
    if top_k != 5:
        raise ValueError("This comparison is defined with a fixed final Top-5 budget")
    rows: list[dict[str, Any]] = []
    strategy_order = ("bm25_only", "bm25_plus_title_bfs_fixed", "bm25_plus_title_bfs_reranked")
    for question in questions:
        scores = bm25_scores(question.question, question.passages)
        graph = build_title_mention_graph(question.passages)
        seed_titles = _bm25_order(scores)[:seed_count]
        bfs_hops = _bfs_hops(seed_titles, graph, scores, max_hops=max_hops)
        title_mention_edges = [
            [source, target]
            for source, neighbors in graph.items()
            for target in neighbors
            if source < target
        ]
        selections = {
            "bm25_only": select_bm25_only(scores, top_k=top_k),
            "bm25_plus_title_bfs_fixed": select_bfs_fixed(
                scores, graph, top_k=top_k, seed_count=seed_count, max_hops=max_hops
            ),
            "bm25_plus_title_bfs_reranked": select_bfs_reranked(
                scores, graph, top_k=top_k, seed_count=seed_count, max_hops=max_hops
            ),
        }
        for strategy in strategy_order:
            selected = selections[strategy]
            retrieved_titles = [item.title for item in selected]
            rows.append(
                {
                    "question_id": question.question_id,
                    "question": question.question,
                    "strategy": strategy,
                    "supporting_titles": list(question.supporting_titles),
                    "retrieved_titles": retrieved_titles,
                    "candidate_passage_count": len(question.passages),
                    "candidate_titles": [passage.title for passage in question.passages],
                    "title_mention_edge_count": sum(len(neighbors) for neighbors in graph.values()) // 2,
                    "title_mention_edges": title_mention_edges,
                    "bfs_seed_titles": seed_titles,
                    "bfs_hops_by_title": dict(sorted(bfs_hops.items())),
                    "selected": [
                        {
                            "title": item.title,
                            "bm25_score": round(item.bm25_score, 6),
                            "rank_score": round(item.rank_score, 6),
                            "origin": item.origin,
                            "hop": item.hop,
                        }
                        for item in selected
                    ],
                    "metrics": compute_retrieval_metrics(
                        retrieved_titles, list(question.supporting_titles), top_k=top_k
                    ),
                }
            )
    summary = {strategy: _summary(rows, strategy) for strategy in strategy_order}
    metric_names = ("recall_at_k", "mrr", "hit_at_1", "ndcg_at_k")
    return {
        "execution_mode": "offline_hotpotqa_title_mention_graph",
        "dataset": "HotpotQA distractor",
        "split": "validation offset 0 length 100, filtered to questions with at least two supporting titles",
        "question_count": len(questions),
        "top_k": top_k,
        "graph_construction": {
            "source": "candidate passage body explicitly mentions another candidate title",
            "uses_gold_supporting_facts": False,
            "undirected_edges": True,
            "minimum_title_alnum_length": MIN_TITLE_ALNUM_LENGTH,
        },
        "strategies": {
            "bm25_only": "BM25 rank over all ten candidate passages",
            "bm25_plus_title_bfs_fixed": "BM25 Top-2 seeds, title-mention BFS up to two hops, then BM25 fill; no rerank",
            "bm25_plus_title_bfs_reranked": "BM25 Top-5 plus title-BFS pool, reranked by normalized BM25 + 0.03 BFS edge bonus - 0.02 per hop",
        },
        "summary": summary,
        "delta_vs_bm25": {
            strategy: {
                metric: round(float(summary[strategy][metric]) - float(summary["bm25_only"][metric]), 4)
                for metric in metric_names
            }
            for strategy in strategy_order[1:]
        },
        "cases": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate title-mention BFS on HotpotQA distractor")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET_PATH))
    parser.add_argument("--query-limit", type=int, default=100)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    questions = load_hotpotqa_questions(args.dataset, limit=args.query_limit)
    if not questions:
        raise ValueError("No eligible HotpotQA questions loaded")
    report = run_hotpotqa_evaluation(questions)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
