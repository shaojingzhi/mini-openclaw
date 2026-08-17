# HotpotQA Title-Mention Graph Evaluation

## Question

The earlier local evaluation could distinguish broader graph candidate coverage
from BFS, but it only contained five hand-labeled cases. This experiment asks a
narrower, reproducible question on public multi-hop data:

> Given HotpotQA's ten visible distractor passages, can title-mention BFS add
> supporting articles to an equal final Top-5 result set?

It is an offline evaluator. It does not change the chat runtime or claim to
measure end-to-end answer quality.

## Dataset And Leakage Boundary

- Dataset: [HotpotQA distractor](https://huggingface.co/datasets/hotpotqa/hotpot_qa), validation split.
- Slice: public rows `offset=0`, `length=100`; after requiring at least two
  distinct supporting titles, 99 questions remained.
- Each question supplies ten candidate Wikipedia passages.
- Gold `supporting_facts.title` is read **only after selection** to calculate
  Recall@5, MRR, Hit@1, and nDCG@5.
- A graph edge is added only when one candidate passage's body explicitly
  contains another candidate passage's normalized title. No gold label is
  passed to graph construction.

This was intentionally kept inside each question's ten passages. It therefore
tests traversal over a supplied candidate set, not open-corpus Wikipedia
retrieval.

## Policies

Every policy returns exactly five distinct article titles:

| Strategy | Candidate / ranking policy |
| --- | --- |
| `bm25_only` | BM25 over all ten candidate passages. |
| `bm25_plus_title_bfs_fixed` | BM25 Top-2 seeds, title-mention BFS to two hops, traversal order first, then BM25 fill. No rerank. |
| `bm25_plus_title_bfs_reranked` | BM25 Top-5 union the same BFS pool, deduplicated and reranked by normalized BM25 plus `0.03` for a BFS candidate minus `0.02` per hop. |

The fixed policy is deliberately an ablation, not a recommended production
ranker: it answers whether BFS coverage can add labeled support before lexical
rank preference restores the baseline ordering.

## Run

```bash
scripts/download_hotpotqa_distractor.sh
.venv/bin/python -m backend.evals.hotpotqa_title_graph \
  --output backend/evals/reports/hotpotqa_title_graph_2026-08-18.json
```

The original sample and detailed JSON report are gitignored. The saved report
contains all ten candidate titles, every title-mention edge, BFS seed and
reachable-hop map, plus each selected title's origin, hop, BM25 score, and
final score for inspection.

## Result

Run on 2026-08-18:

| Strategy | Recall@5 | MRR | Hit@1 | nDCG@5 |
| --- | ---: | ---: | ---: | ---: |
| BM25 only | 0.8485 | 0.8715 | 0.7879 | 0.7857 |
| BM25 + title BFS, fixed order | 0.9293 | 0.8729 | 0.7879 | 0.8359 |
| BM25 + title BFS, lexical rerank | 0.8535 | 0.8715 | 0.7879 | 0.7888 |

The fixed traversal improved Recall@5 by `+0.0808` and nDCG@5 by `+0.0502`
versus BM25. It improved per-question recall on 18 questions, regressed on 2,
and left 79 unchanged. Of the 99 questions, 84 had at least one title-mention
edge.

For example, for “Were Scott Derrickson and Ed Wood of the same nationality?”,
BM25's Top-5 contained `Ed Wood` but omitted `Scott Derrickson`. Starting from
the top lexical seeds, title-mention BFS reached both articles and returned
both supporting titles within Top-5.

## Interpretation And Limits

The positive result is limited to **candidate coverage from visible title
relations**. It does not establish that the project’s production BFS policy is
better, and it does not establish open-domain graph retrieval quality:

- The distractor setting already supplies ten passages, so this does not
  evaluate corpus indexing or first-stage retrieval.
- Title string matching can make noisy or ambiguous edges. A four-character
  minimum removes only the most trivial titles; entity linking or typed
  hyperlinks would be more robust.
- The simple reranker nearly removes the gain: its Recall@5 delta is only
  `+0.0050`. This shows that the value of traversal depends on a better
  confidence/reranking policy, rather than proving every graph expansion is
  useful.
- The experiment evaluates support-title retrieval, not whether a model uses
  the retrieved evidence to answer correctly.

The honest interview claim is: “I separated graph expansion from final ranking
and used HotpotQA distractor to verify that two-hop title traversal can improve
support-document coverage under a fixed Top-5 budget. The first lightweight
reranker mostly erased that gain, so I kept it as a negative finding and would
replace title matching with typed relations plus a trained or LLM-free
cross-encoder reranker before adopting it in production.”
