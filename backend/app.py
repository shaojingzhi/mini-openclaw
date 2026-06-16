"""Mini-OpenClaw FastAPI backend application.

Run with: ``uvicorn backend.app:app --port 8002``
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette import EventSourceResponse
from dotenv import load_dotenv

from backend.graph.agent import build_agent
from backend import sessions_store, traces_store

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

app: FastAPI = FastAPI(title="Mini-OpenClaw Backend")

DEFAULT_CORS_ORIGINS: tuple[str, ...] = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3004",
    "http://127.0.0.1:3004",
)


def _cors_origins() -> list[str]:
    raw_origins = os.getenv("MINI_OPENCLAW_CORS_ORIGINS")
    if not raw_origins:
        return list(DEFAULT_CORS_ORIGINS)
    return [origin.strip() for origin in raw_origins.split(",") if origin.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PROJECT_ROOT: Path = Path(__file__).resolve().parents[1]
ALLOWED_FILE_ROOTS: tuple[Path, ...] = (
    PROJECT_ROOT / "backend" / "memory",
    PROJECT_ROOT / "backend" / "workspace",
    PROJECT_ROOT / "backend" / "skills",
)


class ChatRequest(BaseModel):
    message: str
    session_id: str
    stream: bool = True
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None


class FileWriteRequest(BaseModel):
    path: str
    content: str


class SessionMessage(BaseModel):
    role: str
    content: str


def _resolve_model_name(request: ChatRequest) -> str:
    return request.model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def _resolve_allowed_file_path(raw_path: str) -> Path:
    candidate = (PROJECT_ROOT / raw_path).resolve()
    for root in ALLOWED_FILE_ROOTS:
        try:
            candidate.relative_to(root.resolve())
            return candidate
        except ValueError:
            continue
    raise HTTPException(status_code=403, detail="path is outside allowed roots")


def _coerce_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return str(content) if content is not None else ""


def _session_metadata(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "name": path.stem,
        "last_modified": datetime.fromtimestamp(
            stat.st_mtime,
            tz=timezone.utc,
        ).isoformat(),
        "message_count": len(sessions_store.load_session(path.stem)),
    }


def _extract_final_reply(result: Any) -> str:
    if isinstance(result, dict):
        messages = result.get("messages")
        if isinstance(messages, list) and messages:
            last = messages[-1]
            if isinstance(last, dict):
                return _coerce_text(last.get("content", ""))
            return _coerce_text(getattr(last, "content", ""))
        reply = result.get("reply")
        if isinstance(reply, str):
            return reply
    return _coerce_text(getattr(result, "content", ""))


def _agent_error_message(error: Exception) -> str:
    return str(error).strip() or error.__class__.__name__


async def _invoke_agent(agent: Any, payload: dict[str, Any]) -> Any:
    if hasattr(agent, "ainvoke"):
        return await agent.ainvoke(payload)
    return await asyncio.to_thread(agent.invoke, payload)


async def _stream_agent_events(
    agent: Any,
    payload: dict[str, Any],
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    final_text = ""
    emitted_final = False
    async for raw_event in agent.astream_events(payload, version="v2"):
        event_type = raw_event.get("event_type") or raw_event.get("type")
        if event_type in {"thought", "tool_call", "tool_result", "final"}:
            raw_payload = raw_event.get("data", {})
            if isinstance(raw_payload, dict):
                event_payload = raw_payload
            else:
                event_payload = {"content": _coerce_text(raw_payload)}
            if event_type == "final":
                final_text = _coerce_text(event_payload.get("content", ""))
                emitted_final = True
            yield event_type, event_payload
            continue

        event_name = raw_event.get("event")
        data = raw_event.get("data", {})
        if event_name == "on_tool_start":
            event_payload = {
                "name": raw_event.get("name", "tool"),
                "input": data.get("input"),
            }
            yield "tool_call", event_payload
            continue
        if event_name == "on_tool_end":
            event_payload = {
                "name": raw_event.get("name", "tool"),
                "content": _coerce_text(data.get("output", "")),
            }
            yield "tool_result", event_payload
            continue
        if event_name == "on_chat_model_stream":
            chunk = data.get("chunk")
            text = _coerce_text(getattr(chunk, "content", ""))
            if text:
                final_text += text

    if final_text and not emitted_final:
        yield "final", {"content": final_text}


async def _chat_sse(request: ChatRequest) -> AsyncIterator[dict[str, str]]:
    sessions_store.append_message(
        request.session_id,
        {"role": "user", "content": request.message},
    )
    trace = traces_store.create_trace(
        session_id=request.session_id,
        model_name=_resolve_model_name(request),
    )
    traces_store.append_event(trace, kind="user_message", payload={"content": request.message})
    agent = build_agent(
        api_key=request.api_key,
        base_url=request.base_url,
        model_name=request.model,
    )
    payload = {"messages": sessions_store.load_session(request.session_id)}
    final_text = ""

    try:
        async for event_type, event_payload in _stream_agent_events(agent, payload):
            traces_store.append_event(trace, kind=event_type, payload=event_payload)
            if event_type == "final":
                final_text = _coerce_text(event_payload.get("content", ""))
            yield {
                "event": event_type,
                "data": json.dumps(event_payload, ensure_ascii=False),
            }
        traces_store.finalize_trace(trace, final_status="success")
    except Exception as exc:
        final_text = "The assistant could not complete the request."
        error_payload = {
            "name": "agent_error",
            "content": _agent_error_message(exc),
        }
        traces_store.append_event(trace, kind="tool_result", payload=error_payload)
        traces_store.append_event(trace, kind="final", payload={"content": final_text})
        traces_store.finalize_trace(trace, final_status="error")
        yield {
            "event": "tool_result",
            "data": json.dumps(error_payload, ensure_ascii=False),
        }
        yield {
            "event": "final",
            "data": json.dumps({"content": final_text}, ensure_ascii=False),
        }

    sessions_store.append_message(
        request.session_id,
        {"role": "assistant", "content": final_text},
    )
    traces_store.save_trace(trace)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/chat", response_model=None)
async def chat(request: ChatRequest) -> Any:
    if request.stream:
        return EventSourceResponse(_chat_sse(request))

    sessions_store.append_message(
        request.session_id,
        {"role": "user", "content": request.message},
    )
    trace = traces_store.create_trace(
        session_id=request.session_id,
        model_name=_resolve_model_name(request),
    )
    traces_store.append_event(trace, kind="user_message", payload={"content": request.message})
    agent = build_agent(
        api_key=request.api_key,
        base_url=request.base_url,
        model_name=request.model,
    )
    try:
        result = await _invoke_agent(
            agent,
            {"messages": sessions_store.load_session(request.session_id)},
        )
        final_text = _extract_final_reply(result)
        traces_store.append_event(trace, kind="final", payload={"content": final_text})
        traces_store.finalize_trace(trace, final_status="success")
    except Exception as exc:
        error_message = _agent_error_message(exc)
        traces_store.append_event(
            trace,
            kind="tool_result",
            payload={"name": "agent_error", "content": error_message},
        )
        traces_store.finalize_trace(trace, final_status="error")
        traces_store.save_trace(trace)
        raise HTTPException(
            status_code=502,
            detail=f"agent execution failed: {error_message}",
        ) from exc
    sessions_store.append_message(
        request.session_id,
        {"role": "assistant", "content": final_text},
    )
    traces_store.save_trace(trace)
    return {"reply": final_text, "trace_id": trace["trace_id"]}


@app.get("/api/files")
def get_file(path: str) -> dict[str, str]:
    resolved_path = _resolve_allowed_file_path(path)
    try:
        content = resolved_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="file not found") from exc
    return {"path": path, "content": content}


@app.post("/api/files")
def save_file(request: FileWriteRequest) -> dict[str, str]:
    resolved_path = _resolve_allowed_file_path(request.path)
    resolved_path.write_text(request.content, encoding="utf-8")
    return {"path": request.path, "content": request.content}


@app.get("/api/sessions")
def list_sessions() -> dict[str, list[dict[str, Any]]]:
    if not sessions_store.SESSIONS_DIR.exists():
        return {"sessions": []}

    sessions = [
        _session_metadata(path)
        for path in sorted(sessions_store.SESSIONS_DIR.glob("*.json"))
        if path.is_file()
    ]
    return {"sessions": sessions}


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str) -> dict[str, Any]:
    messages = sessions_store.load_session(session_id)
    return {"session_id": session_id, "messages": messages}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.app:app", host="0.0.0.0", port=8002, reload=False)
