# Failure Matrix

This matrix tracks the most common local-agent failure edges that Mini-OpenClaw now covers with tests and/or friendly fallbacks.

| Surface | Scenario | Expected behavior | Coverage |
| --- | --- | --- | --- |
| `/api/chat` | Recoverable timeout before output | Retry once, then continue or return a friendly categorized failure | `backend/tests/test_api_chat.py` |
| `/api/chat` | Non-recoverable invalid input / schema issue | Return non-silent JSON error payload with `error_category` and friendly message | `backend/tests/test_api_chat.py` |
| `/api/chat` streaming | Failure before final answer | Emit SSE `tool_result` + `final` fallback instead of hanging | `backend/tests/test_api_chat.py` |
| `terminal` | Blacklisted destructive command | Refuse execution with a fixed safety message | `backend/tests/test_terminal.py` |
| `terminal` | Invalid shell command | Return shell error output without crashing | `backend/tests/test_terminal.py` |
| `read_file` | Missing in-project file | Return explicit missing-file message | `backend/tests/test_read_file.py` |
| `/api/files` | Missing allowed file | Return HTTP `404` with `file not found` payload | `backend/tests/test_api_files.py` |
| `fetch_url` | HTML/Markdown parse failure | Return a friendly parse-failure message | `backend/tests/test_fetch_url.py` |
| `search_knowledge_base` | Empty knowledge directory | Return `EMPTY_KB_MESSAGE` | `backend/tests/test_search_knowledge_base.py` |
| `search_knowledge_base` | No retrieval matches | Return `NO_RESULTS_MESSAGE` | `backend/tests/test_search_knowledge_base.py` |
| `search_knowledge_base` | Embedding package unavailable | Fall back to mock embeddings instead of crashing test/runtime setup | `backend/tools/search_knowledge_base.py` + `backend/tests/test_search_knowledge_base.py` |

## Notes

- The goal is not to hide failures; it is to make them explicit, typed, and recoverable when possible.
- API responses should always give the frontend enough signal to render a useful state instead of hanging on a spinner.
- Trace payloads are the source of truth for post-run diagnostics, including error category, retry count, and friendly fallback text.
