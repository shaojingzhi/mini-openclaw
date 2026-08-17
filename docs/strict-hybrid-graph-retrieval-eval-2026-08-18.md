# Strict Hybrid Plus Graph Retrieval Evaluation

## Why A Second Experiment

The first live graph evaluation showed that the production graph evidence
selection did not improve ranking. It compared the graph layer in isolation.
This follow-up evaluates the more defensible retrieval design:

```text
hybrid retrieval candidates
+ graph direct and BFS candidates
-> source-path deduplication
-> query-aware lexical rerank
-> fixed final Top-5 evidence budget
```

The baseline receives the same final budget and uses only the existing hybrid
BM25 + vector candidates.

## Fairness Fixes

The experiment found and fixed one retrieval bug before measuring: the hybrid
index previously read only the top-level knowledge directory, omitting nested
files such as `backend/knowledge/interview/*.md`. The search tool now indexes
the knowledge directory recursively. The evaluator also builds a fresh
temporary index for every run, so a stale persisted index cannot suppress
newly added documents.

## Setup

- Five manually path-labeled multi-artifact questions from
  `backend/evals/datasets/live_graph_retrieval.json`.
- A graph built at runtime from local knowledge, workspace, skills, and trace
  artifacts: 217 nodes and 259 edges in this run.
- Final evidence budget: five source artifacts for every strategy.
- Graph candidates: direct graph matches plus up to two-hop BFS expansion.
- Reranker: deterministic lexical term-overlap score, plus a documented small
  hybrid-origin bonus, edge-type bonus, and hop penalty. This is not a learned
  or cross-encoder reranker.

Run it with:

```bash
.venv/bin/python -m backend.evals.strict_hybrid_graph_retrieval \
  --output backend/evals/reports/strict_hybrid_graph_retrieval_2026-08-18.json
```

## Result

| Strategy | Recall@5 | MRR | Hit@1 | nDCG@5 |
| --- | ---: | ---: | ---: | ---: |
| Hybrid only | 0.3667 | 0.8000 | 0.8000 | 0.4681 |
| Hybrid + graph direct + rerank | 0.6167 | 0.8500 | 0.8000 | 0.6189 |
| Hybrid + graph direct + BFS + rerank | 0.6167 | 0.8500 | 0.8000 | 0.6189 |

Compared with hybrid only, the combined candidate pool improved Recall@5 by
0.2500, MRR by 0.0500, and nDCG@5 by 0.1508. The full JSON report preserves
every candidate path, origin, hop count, edge type, and rerank score.

## Interpretation

This is a narrowly scoped positive result for **cross-artifact candidate
coverage plus deterministic reranking**. It is not evidence that BFS improves
retrieval quality:

- The direct-graph and BFS-graph rows are identical in all four metrics.
- None of the final Top-5 candidates in this labeled slice required a BFS
  candidate to beat the direct graph candidates after reranking.
- The graph's measured benefit comes from making workspace, skill, and trace
  artifacts available to the candidate pool, while hybrid retrieval indexes
  knowledge documents only.

Therefore the production runtime should not yet claim that BFS itself has a
validated positive effect. The earlier negative result remains relevant for
the current production policy that appends fixed graph evidence without a
shared rerank stage.

## Next Validation Step

To test BFS rather than merely broader candidate coverage, add cases where a
relevant source has no direct lexical match but is reachable through a strong,
typed relation. Evaluate at least three buckets separately: direct lookup,
cross-artifact aggregation, and true multi-hop reasoning. Only then decide
whether BFS candidates should be injected into the runtime prompt or gated by
a confidence threshold.
