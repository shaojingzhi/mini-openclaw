# Retrieval Benchmark Plan

## Why Two Benchmark Families

Mini-OpenClaw needs separate evidence for baseline retrieval quality and for
multi-artifact graph expansion. A generic retrieval dataset does not prove that
BFS is useful, because it usually has no trustworthy relationship edges.

## BEIR SciFact: Baseline Retrieval

[BEIR SciFact](https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/scifact.zip)
is a compact public scientific-claim retrieval collection with a document
corpus, test queries, and relevance judgments. It is used here only to measure
the existing BM25 + vector hybrid retriever on a standard corpus.

```bash
scripts/download_beir_scifact.sh
.venv/bin/python -m backend.evals.beir_scifact \
  --output backend/evals/reports/beir_scifact_hybrid.json
```

The downloaded corpus stays under `backend/evals/benchmarks/`, which is
gitignored. Commit the runner and a compact report, not the third-party corpus.

### Local Reference Run

On 2026-08-18, the current retriever ran the complete SciFact test split: 300
queries against 5,183 document abstracts, with a final budget of five results.
The runner reported `hybrid_bm25_vector` and produced:

| Recall@5 | MRR | Hit@1 | nDCG@5 |
| ---: | ---: | ---: | ---: |
| 0.7387 | 0.6385 | 0.5533 | 0.6590 |

This is a local reference result for the current implementation, not a BEIR
leaderboard claim. It is not comparable to published results that use different
embedding models, query encoders, preprocessing, or retrieval budgets. It also
does not validate graph traversal.

## Multi-Hop Data: A Separate Claim

Use a small, documented subset of HotpotQA or MuSiQue for a later multi-hop
experiment. Build graph edges from information available at retrieval time,
such as titles, hyperlinks, or extracted entities. Do not build edges from gold
supporting-fact annotations: that would leak labels into candidate generation.

For a credible graph result, compare equal final evidence budgets and report
three buckets separately:

1. Direct lookup: graph expansion should usually fall back to hybrid retrieval.
2. Cross-artifact aggregation: graph candidates may improve source coverage.
3. True multi-hop reasoning: only claim a BFS gain when expanded nodes add
   labeled supporting evidence after reranking.

## Interview Boundary

BEIR validates general retrieval plumbing, not Mini-OpenClaw's agent behavior
or graph traversal. The local path-labeled evaluations validate system-specific
evidence selection. Report both scopes separately.
