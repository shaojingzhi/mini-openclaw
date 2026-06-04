"""Agent factory using LangChain 1.x `create_agent`.

Builds a single Agent wired with the five core tools (``terminal``,
``python_repl``, ``fetch_url``, ``read_file``, ``search_knowledge_base``)
and the assembled System Prompt produced by ``backend.prompt_assembler``.

The model client is OpenAI-API-compatible (OpenRouter / DeepSeek / vLLM /
LM Studio / etc.) — `base_url`, `api_key`, and `model` are read from
environment variables so deployments can swap providers without touching
code.

Environment variables (all optional with sensible defaults):
    OPENAI_API_KEY      OpenAI-compatible API key. Falls back to "EMPTY"
                        so local servers like LM Studio that ignore the
                        key still work without the user setting it.
    OPENAI_BASE_URL     OpenAI-compatible base URL (e.g.
                        ``https://openrouter.ai/api/v1``). Unset means
                        the upstream default (api.openai.com).
    OPENAI_MODEL        Model identifier to send to the provider
                        (default ``gpt-4o-mini``).
"""

from __future__ import annotations

import os
from typing import Any

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from backend.prompt_assembler import build_system_prompt
from backend.tools import (
    fetch_url,
    python_repl,
    read_file,
    search_knowledge_base,
    terminal,
)

DEFAULT_MODEL = "gpt-4o-mini"

CORE_TOOLS = [terminal, python_repl, fetch_url, read_file, search_knowledge_base]


def _build_model() -> BaseChatModel:
    """Instantiate the OpenAI-API-compatible chat model from environment vars."""
    api_key = os.environ.get("OPENAI_API_KEY", "EMPTY")
    base_url = os.environ.get("OPENAI_BASE_URL")
    model = os.environ.get("OPENAI_MODEL", DEFAULT_MODEL)
    kwargs: dict[str, Any] = {"model": model, "api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    return ChatOpenAI(**kwargs)


def build_agent(model: BaseChatModel | None = None) -> Any:
    """Build the Mini-OpenClaw Agent.

    Parameters
    ----------
    model:
        Optional pre-built chat model. When ``None`` (the default) a
        ``ChatOpenAI`` instance is constructed from the OPENAI_* env
        vars. Tests pass a mock here to exercise the agent without
        hitting a real LLM.

    Returns
    -------
    The compiled LangGraph state graph produced by ``create_agent``.
    """
    chat_model = model if model is not None else _build_model()
    system_prompt = build_system_prompt()
    return create_agent(
        model=chat_model,
        tools=CORE_TOOLS,
        system_prompt=system_prompt,
    )
