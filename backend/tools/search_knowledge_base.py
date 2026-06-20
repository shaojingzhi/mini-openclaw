"""Hybrid knowledge-base search tool for the Mini-OpenClaw agent (US-008).

Combines a BM25 lexical retriever with a vector retriever over the documents
under ``backend/knowledge/`` and returns the fused top-k passages. The
underlying ``VectorStoreIndex`` is persisted under ``backend/storage/`` and
reloaded on subsequent calls/startups so cold start does not pay the
embedding cost twice.

Design notes:

- Heavy LlamaIndex imports are deferred to the first ``invoke()`` call so
  module import (and the ``@tool`` decoration) stays cheap.
- ``Settings.embed_model`` defaults to a deterministic ``MockEmbedding``
  when ``OPENAI_API_KEY`` is not in the environment. BM25 remains a real
  keyword retriever in either case, so the tool gives useful results even
  without API credentials.
- ``Settings.llm`` is forced to ``MockLLM`` because we never need
  synthesis; ``QueryFusionRetriever`` with ``num_queries=1`` skips the
  LLM-based query rewriting step entirely.
"""

from __future__ import annotations

import os
from pathlib import Path
from threading import Lock
from typing import Any, Iterable

from langchain_core.tools import tool

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
KNOWLEDGE_DIR: Path = PROJECT_ROOT / "backend" / "knowledge"
STORAGE_DIR: Path = PROJECT_ROOT / "backend" / "storage"

EMPTY_KB_MESSAGE: str = (
    "Knowledge base is empty: no readable files were found under "
    "backend/knowledge/. Add PDF, MD, or TXT documents there to enable "
    "knowledge-base search."
)
NO_RESULTS_MESSAGE: str = "No matching passages found in the knowledge base."

_retriever_cache: dict[tuple[str, str], Any] = {}
_cache_lock: Lock = Lock()


def clear_cache() -> None:
    """Drop the cached hybrid retriever.

    Tests call this between cases to force a fresh build against
    monkey-patched ``KNOWLEDGE_DIR`` / ``STORAGE_DIR``.
    """
    with _cache_lock:
        _retriever_cache.clear()


def _knowledge_files(knowledge_dir: Path) -> list[Path]:
    if not knowledge_dir.exists():
        return []
    return [
        p
        for p in knowledge_dir.iterdir()
        if p.is_file() and not p.name.startswith(".")
    ]


def _configure_settings() -> None:
    from llama_index.core import Settings
    from llama_index.core.embeddings import MockEmbedding
    from llama_index.core.llms import MockLLM

    Settings.llm = MockLLM()
    if not os.getenv("OPENAI_API_KEY"):
        Settings.embed_model = MockEmbedding(embed_dim=384)
        return

    try:
        from llama_index.embeddings.openai import OpenAIEmbedding

        Settings.embed_model = OpenAIEmbedding()
    except Exception:
        Settings.embed_model = MockEmbedding(embed_dim=384)


def _build_or_load_index(knowledge_dir: Path, storage_dir: Path) -> Any:
    from llama_index.core import (
        SimpleDirectoryReader,
        StorageContext,
        VectorStoreIndex,
        load_index_from_storage,
    )

    if (storage_dir / "docstore.json").exists():
        try:
            ctx = StorageContext.from_defaults(persist_dir=str(storage_dir))
            return load_index_from_storage(ctx)
        except Exception:
            # Persisted index is missing/corrupt — fall through and rebuild.
            pass

    documents = SimpleDirectoryReader(input_dir=str(knowledge_dir)).load_data()
    index = VectorStoreIndex.from_documents(documents)
    storage_dir.mkdir(parents=True, exist_ok=True)
    index.storage_context.persist(persist_dir=str(storage_dir))
    return index


def _build_hybrid_retriever(knowledge_dir: Path, storage_dir: Path) -> Any | None:
    files = _knowledge_files(knowledge_dir)
    if not files:
        return None

    _configure_settings()

    from llama_index.core.retrievers import (
        QueryFusionRetriever,
        VectorIndexRetriever,
    )
    from llama_index.retrievers.bm25 import BM25Retriever

    index = _build_or_load_index(knowledge_dir, storage_dir)
    nodes = list(index.docstore.docs.values())

    bm25 = BM25Retriever.from_defaults(nodes=nodes, similarity_top_k=5)
    vector = VectorIndexRetriever(index=index, similarity_top_k=5)
    return QueryFusionRetriever(
        retrievers=[bm25, vector],
        similarity_top_k=5,
        num_queries=1,
        mode="reciprocal_rerank",
        use_async=False,
        verbose=False,
    )


def _get_retriever() -> Any | None:
    key = (str(KNOWLEDGE_DIR), str(STORAGE_DIR))
    with _cache_lock:
        if key not in _retriever_cache:
            _retriever_cache[key] = _build_hybrid_retriever(
                KNOWLEDGE_DIR, STORAGE_DIR
            )
        return _retriever_cache[key]


def _format_nodes(nodes: Iterable[Any]) -> str:
    parts: list[str] = []
    for i, node in enumerate(nodes, start=1):
        text = node.get_content().strip()
        meta = getattr(node, "metadata", None) or {}
        source = meta.get("file_name") or meta.get("file_path") or "<unknown>"
        score = getattr(node, "score", None)
        header = f"[{i}] {source}"
        if isinstance(score, float):
            header += f" (score={score:.4f})"
        parts.append(f"{header}\n{text}")
    return "\n\n".join(parts)


@tool("search_knowledge_base")
def search_knowledge_base(query: str) -> str:
    """Search the local knowledge base using hybrid BM25 + vector retrieval.

    Files under ``backend/knowledge/`` (markdown, text, PDF) are indexed
    on first use and the index is persisted under ``backend/storage/``
    for reuse across restarts. Returns a clear message if the knowledge
    folder is empty or if no passages match the query.

    Args:
        query: A natural-language or keyword query.

    Returns:
        Top-k formatted passages with source filenames, or a message
        explaining why no results are returned.
    """
    retriever = _get_retriever()
    if retriever is None:
        return EMPTY_KB_MESSAGE
    nodes = retriever.retrieve(query)
    if not nodes:
        return NO_RESULTS_MESSAGE
    return _format_nodes(nodes)


__all__ = [
    "search_knowledge_base",
    "PROJECT_ROOT",
    "KNOWLEDGE_DIR",
    "STORAGE_DIR",
    "EMPTY_KB_MESSAGE",
    "NO_RESULTS_MESSAGE",
    "clear_cache",
]
