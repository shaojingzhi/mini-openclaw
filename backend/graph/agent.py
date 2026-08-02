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

from collections.abc import Callable
from typing import Any

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from backend.prompt_assembler import build_system_prompt
from backend.settings import get_settings
from backend.tools import (
    build_propose_memory_update_tool,
    fetch_url,
    python_repl,
    read_file,
    search_knowledge_base,
    terminal,
)

CORE_TOOLS = [terminal, python_repl, fetch_url, read_file, search_knowledge_base]


def _build_model(
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
) -> BaseChatModel:
    """Instantiate the OpenAI-compatible chat model from env vars or overrides."""
    settings = get_settings()
    resolved_api_key = api_key or settings.openai_api_key
    resolved_base_url = base_url or settings.openai_base_url
    resolved_model = model or settings.openai_model
    kwargs: dict[str, Any] = {
        "model": resolved_model,
        "api_key": resolved_api_key,
    }
    if resolved_base_url:
        kwargs["base_url"] = resolved_base_url
    return ChatOpenAI(**kwargs)


def build_agent(
    model: BaseChatModel | None = None,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    model_name: str | None = None,
    user_id: str = "anonymous",
    session_id: str | None = None,
    approved_memories: list[dict[str, Any]] | None = None,
    on_memory_proposal_created: Callable[[dict[str, Any]], None] | None = None,
) -> Any:
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
    chat_model = model if model is not None else _build_model(
        api_key=api_key,
        base_url=base_url,
        model=model_name,
    )
    system_prompt = build_system_prompt(approved_memories=approved_memories)
    tools = [
        *CORE_TOOLS,
        build_propose_memory_update_tool(
            user_id=user_id,
            session_id=session_id,
            on_proposal_created=on_memory_proposal_created,
        ),
    ]
    return create_agent(
        model=chat_model,
        tools=tools,
        system_prompt=system_prompt,
    )
