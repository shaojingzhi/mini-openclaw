"""Mini-OpenClaw FastAPI backend application.

Run with: ``uvicorn backend.app:app --port 8002``
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel
from sse_starlette import EventSourceResponse

from backend.graph.agent import build_agent
from backend.sessions_store import append_message, load_session

app: FastAPI = FastAPI(title="Mini-OpenClaw Backend")


class ChatRequest(BaseModel):
    message: str
    session_id: str
    stream: bool = True


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
    append_message(request.session_id, {"role": "user", "content": request.message})
    agent = build_agent()
    payload = {"messages": load_session(request.session_id)}
    final_text = ""

    async for event_type, event_payload in _stream_agent_events(agent, payload):
        if event_type == "final":
            final_text = _coerce_text(event_payload.get("content", ""))
        yield {
            "event": event_type,
            "data": json.dumps(event_payload, ensure_ascii=False),
        }

    append_message(request.session_id, {"role": "assistant", "content": final_text})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/chat", response_model=None)
async def chat(request: ChatRequest) -> Any:
    if request.stream:
        return EventSourceResponse(_chat_sse(request))

    append_message(request.session_id, {"role": "user", "content": request.message})
    agent = build_agent()
    result = await _invoke_agent(agent, {"messages": load_session(request.session_id)})
    final_text = _extract_final_reply(result)
    append_message(request.session_id, {"role": "assistant", "content": final_text})
    return {"reply": final_text}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.app:app", host="0.0.0.0", port=8002, reload=False)
