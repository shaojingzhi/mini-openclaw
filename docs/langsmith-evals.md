# LangSmith Evals

Mini-OpenClaw keeps the local offline eval runner, but it can now mirror the
seed datasets into LangSmith for inspection and later experiment tracking.

## Sync Datasets

```bash
.venv/bin/python -m backend.evals.runner \
  --dataset backend/evals/datasets/core_tasks.json \
  --output backend/evals/reports/latest.json \
  --langsmith-sync
```

This will:

- keep writing the local JSON and Markdown reports
- create or reuse the LangSmith datasets for the core tasks and retrieval cases
- skip LangSmith sync cleanly if no API key is configured

## Environment

| Variable | Purpose |
| --- | --- |
| `LANGSMITH_API_KEY` or `LANGCHAIN_API_KEY` | Enables LangSmith sync |
| `LANGSMITH_ENDPOINT` or `LANGCHAIN_ENDPOINT` | Optional custom LangSmith API URL |
| `MINI_OPENCLAW_LANGSMITH_PROJECT` | Project label shown in the local sync summary |

## Notes

- The current migration only mirrors datasets and metadata.
- Local JSON and Markdown reports remain the source of truth until the next
  story wires a live `evaluate(...)` experiment into the runner.
