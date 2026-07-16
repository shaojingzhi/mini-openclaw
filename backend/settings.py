"""Typed runtime settings for Mini-OpenClaw.

The project intentionally avoids adding ``pydantic-settings`` for now. This
module keeps the same typed-settings shape with Pydantic ``BaseModel`` plus
explicit ``.env`` / environment loading.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Final

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
DEFAULT_CORS_ORIGINS: Final[tuple[str, ...]] = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3004",
    "http://127.0.0.1:3004",
)

load_dotenv(PROJECT_ROOT / ".env")


class RuntimeSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    project_root: Path
    openai_api_key: str
    openai_base_url: str | None
    openai_model: str
    backend_host: str
    backend_port: int
    cors_origins: tuple[str, ...]
    knowledge_dir: Path
    storage_dir: Path
    graph_dir: Path
    graph_path: Path
    memory_dir: Path
    workspace_dir: Path
    skills_dir: Path
    traces_dir: Path
    retrieval_top_k: int
    python_repl_timeout_seconds: float
    python_repl_memory_limit_bytes: int
    langsmith_api_key: str | None
    langsmith_endpoint: str | None
    langsmith_project: str


def _optional_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _optional_env_any(*names: str) -> str | None:
    for name in names:
        value = _optional_env(name)
        if value is not None:
            return value
    return None


def _env_int(name: str, default: int) -> int:
    value = _optional_env(name)
    return int(value) if value is not None else default


def _env_float(name: str, default: float) -> float:
    value = _optional_env(name)
    return float(value) if value is not None else default


def _env_path(name: str, default: Path) -> Path:
    value = _optional_env(name)
    path = Path(value) if value is not None else default
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _env_csv(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = _optional_env(name)
    if value is None:
        return default
    return tuple(item.strip() for item in value.split(",") if item.strip())


@lru_cache(maxsize=1)
def get_settings() -> RuntimeSettings:
    graph_dir = _env_path(
        "MINI_OPENCLAW_GRAPH_DIR",
        PROJECT_ROOT / "backend" / "data" / "graph",
    )
    return RuntimeSettings(
        project_root=PROJECT_ROOT,
        openai_api_key=os.getenv("OPENAI_API_KEY", "EMPTY"),
        openai_base_url=_optional_env("OPENAI_BASE_URL"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        backend_host=os.getenv("MINI_OPENCLAW_BACKEND_HOST", "0.0.0.0"),
        backend_port=_env_int("MINI_OPENCLAW_BACKEND_PORT", 8002),
        cors_origins=_env_csv("MINI_OPENCLAW_CORS_ORIGINS", DEFAULT_CORS_ORIGINS),
        knowledge_dir=_env_path(
            "MINI_OPENCLAW_KNOWLEDGE_DIR",
            PROJECT_ROOT / "backend" / "knowledge",
        ),
        storage_dir=_env_path(
            "MINI_OPENCLAW_STORAGE_DIR",
            PROJECT_ROOT / "backend" / "storage",
        ),
        graph_dir=graph_dir,
        graph_path=_env_path(
            "MINI_OPENCLAW_GRAPH_PATH",
            graph_dir / "knowledge_graph.json",
        ),
        memory_dir=_env_path(
            "MINI_OPENCLAW_MEMORY_DIR",
            PROJECT_ROOT / "backend" / "memory",
        ),
        workspace_dir=_env_path(
            "MINI_OPENCLAW_WORKSPACE_DIR",
            PROJECT_ROOT / "backend" / "workspace",
        ),
        skills_dir=_env_path(
            "MINI_OPENCLAW_SKILLS_DIR",
            PROJECT_ROOT / "backend" / "skills",
        ),
        traces_dir=_env_path(
            "MINI_OPENCLAW_TRACES_DIR",
            PROJECT_ROOT / "backend" / "data" / "traces",
        ),
        retrieval_top_k=_env_int("MINI_OPENCLAW_RETRIEVAL_TOP_K", 5),
        python_repl_timeout_seconds=_env_float(
            "MINI_OPENCLAW_PYTHON_REPL_TIMEOUT_SECONDS",
            3.0,
        ),
        python_repl_memory_limit_bytes=_env_int(
            "MINI_OPENCLAW_PYTHON_REPL_MEMORY_LIMIT_BYTES",
            256 * 1024 * 1024,
        ),
        langsmith_api_key=_optional_env_any("LANGSMITH_API_KEY", "LANGCHAIN_API_KEY"),
        langsmith_endpoint=_optional_env_any(
            "LANGSMITH_ENDPOINT",
            "LANGCHAIN_ENDPOINT",
        ),
        langsmith_project=os.getenv(
            "MINI_OPENCLAW_LANGSMITH_PROJECT",
            "mini-openclaw-evals",
        ),
    )


__all__ = ["DEFAULT_CORS_ORIGINS", "RuntimeSettings", "get_settings"]
