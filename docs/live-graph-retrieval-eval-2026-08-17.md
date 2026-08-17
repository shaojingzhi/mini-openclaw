# Live Graph Retrieval Evaluation: A Useful Negative Result

## Question

Does the current graph-assisted evidence path improve retrieval over a direct
source match for multi-artifact Mini-OpenClaw questions?

The answer for the current implementation is: not yet.

## Reproducible Setup

- Dataset: five manually labeled multi-hop questions in
  `backend/evals/datasets/live_graph_retrieval.json`.
- Corpus: the graph built at evaluation time from local knowledge, workspace,
  skills, and trace artifacts.
- Graph size: 217 nodes and 259 edges.
- Direct strategy: the top five source artifacts matched before graph
  expansion.
- Graph strategy: the source artifacts selected by the production graph
  evidence policy (up to four direct and four 2-hop-expanded nodes), evaluated
  at `K=5` after source-path deduplication.
- Runner: `python -m backend.evals.live_graph_retrieval --output <report>`.

The committed JSON report is
`backend/evals/reports/live_graph_retrieval_2026-08-17.json`. It records each
query, its labeled paths, retrieved paths, and per-case metrics.

## Result

| Strategy | Recall@5 | MRR | Hit@1 | nDCG@5 |
| --- | ---: | ---: | ---: | ---: |
| Direct graph match | 0.7333 | 0.7667 | 0.6000 | 0.6733 |
| Graph-assisted evidence | 0.4833 | 0.7000 | 0.6000 | 0.5195 |
| Delta | -0.2500 | -0.0667 | 0.0000 | -0.1538 |

This is a real execution over the current graph, not the older fixture-based
retrieval metrics. It must not be represented as a general benchmark or as a
positive Graph RAG result.

## What The Result Means

The graph path is functioning: it traverses relationships and changes the
evidence set. It simply does not improve ranking for this labeled slice and
evidence budget. In particular, `Hit@1` is unchanged while recall and nDCG
fall, so the expansion contributes context but displaces relevant direct
evidence too often.

This is a targeted retrieval-quality observation, not evidence that graph
structure is always useless. It is also not an answer-quality evaluation: no
generation model or LLM judge was used here.

## Likely Causes

1. The direct matcher already finds many relevant source summaries. Expansion
   has limited recall headroom on these questions.
2. The current display policy reserves a fixed evidence budget for expanded
   nodes. After path deduplication, the expanded set can contain fewer useful
   source artifacts than the direct top five.
3. `contains` and `mentions` edges are structural and currently unweighted.
   Structural proximity is not the same as query relevance.
4. BFS candidates are not reranked against the query after expansion, so a
   generic neighbor can displace a stronger direct match.
5. The graph is intentionally lightweight and local-file based. It lacks the
   learned entity resolution, relation weighting, and community summaries of a
   full GraphRAG system.

## Improvement Plan

1. Treat BFS as candidate generation only: keep the direct top-k and expand
   one or two hops into a separate candidate pool.
2. Deduplicate candidates by source path, then rerank with a query-aware score
   that combines direct relevance, edge-type weight, and hop penalty.
3. Give `references` and explicit skill/tool relations higher weights than
   generic `mentions`; penalize generic concepts and second-hop evidence.
4. Add a confidence gate: when expanded candidates cannot beat the direct
   relevance threshold, fall back to direct retrieval rather than forcing graph
   evidence into the prompt.
5. Split the evaluation set by question type and report per-bucket outcomes:
   single-document lookup, cross-artifact explanation, and multi-hop reasoning.

## Interview Framing

Use this as an engineering judgment story, not a victory lap:

> I added an inspectable graph-evidence layer, then replaced fixture metrics
> with a live path-labeled evaluation. The first result showed BFS expansion
> hurt Recall@5 by 0.25 on five multi-hop cases because structural neighbors
> displaced stronger direct evidence. I therefore treat graph traversal as
> candidate generation and would add query-aware reranking and a fallback gate
> before claiming a retrieval-quality gain.
