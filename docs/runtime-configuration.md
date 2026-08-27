# Mini-OpenClaw Runtime Configuration

Mini-OpenClaw reads runtime configuration through `backend/settings.py`. Values
come from environment variables and the optional repo-level `.env` file.

## Model Provider

| Variable | Default | Purpose |
| --- | --- | --- |
| `OPENAI_API_KEY` | `EMPTY` | OpenAI-compatible API key. Local providers that ignore keys can use the default. |
| `OPENAI_BASE_URL` | unset | OpenAI-compatible provider URL, such as OpenRouter, LM Studio, vLLM, or Ollama gateway. |
| `OPENAI_MODEL` | `gpt-4o-mini` | Chat model name sent to the provider. |

## Server

| Variable | Default | Purpose |
| --- | --- | --- |
| `MINI_OPENCLAW_BACKEND_HOST` | `0.0.0.0` | Host used when running `python -m backend.app`. |
| `MINI_OPENCLAW_BACKEND_PORT` | `8002` | Backend port. |
| `MINI_OPENCLAW_CORS_ORIGINS` | localhost/127.0.0.1 ports `3000` and `3004` | Comma-separated frontend origins. It must include the exact frontend origin opened in the browser, for example `http://127.0.0.1:3000`. |

`NEXT_PUBLIC_API_URL` is a frontend build-time variable, not a backend setting. Point it to the backend URL that the browser can reach. For a custom frontend port, set `MINI_OPENCLAW_CORS_ORIGINS` to that frontend origin before starting the backend; do not use wildcard origins with credentialed requests.

## Storage And Retrieval

| Variable | Default | Purpose |
| --- | --- | --- |
| `MINI_OPENCLAW_KNOWLEDGE_DIR` | `backend/knowledge` | Source documents for knowledge retrieval. |
| `MINI_OPENCLAW_STORAGE_DIR` | `backend/storage` | Persisted LlamaIndex storage. |
| `MINI_OPENCLAW_GRAPH_DIR` | `backend/data/graph` | Generated graph directory. |
| `MINI_OPENCLAW_GRAPH_PATH` | `backend/data/graph/knowledge_graph.json` | Generated graph JSON path. |
| `MINI_OPENCLAW_RETRIEVAL_TOP_K` | `5` | BM25/vector/fusion retrieval top-k. |

## Tool Limits

| Variable | Default | Purpose |
| --- | --- | --- |
| `MINI_OPENCLAW_PYTHON_REPL_TIMEOUT_SECONDS` | `3.0` | Wall-clock timeout for `python_repl`. |
| `MINI_OPENCLAW_PYTHON_REPL_MEMORY_LIMIT_BYTES` | `268435456` | Best-effort subprocess memory limit. |

## LangSmith

| Variable | Default | Purpose |
| --- | --- | --- |
| `LANGSMITH_API_KEY` or `LANGCHAIN_API_KEY` | unset | Enables LangSmith dataset sync. |
| `LANGSMITH_ENDPOINT` or `LANGCHAIN_ENDPOINT` | unset | Optional custom LangSmith API endpoint. |
| `MINI_OPENCLAW_LANGSMITH_PROJECT` | `mini-openclaw-evals` | Label used in sync summaries. |

Relative paths are resolved against the repository root. Absolute paths are
used as-is.
