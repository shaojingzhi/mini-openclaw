"""Mini-OpenClaw FastAPI backend application.

Run with: ``uvicorn backend.app:app --port 8002``
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette import EventSourceResponse
from fastapi.responses import JSONResponse

from backend import sessions_store, traces_store
from backend.evals.jobs import get_eval_job, submit_eval_job
from backend.evals.runner import DEFAULT_DATASET_PATH, DEFAULT_PROFILES_PATH
from backend.graph.agent import build_agent
from backend.graph import index as graph_index
from backend.runtime_errors import classify_runtime_failure, runtime_error_payload, should_retry_runtime_failure
from backend.settings import get_settings
from backend.user_locks import run_with_user_lock
from backend.user_state import DEFAULT_USER_ID, normalize_user_id, user_memory_dir, user_sessions_dir, user_workspace_dir

app: FastAPI = FastAPI(title="Mini-OpenClaw Backend")


def _cors_origins() -> list[str]:
    return list(get_settings().cors_origins)


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PROJECT_ROOT: Path = get_settings().project_root
ALLOWED_FILE_ROOTS: tuple[Path, ...] = (
    get_settings().memory_dir,
    get_settings().workspace_dir,
    get_settings().skills_dir,
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


class GraphDemoRequest(BaseModel):
    session_id: str
    message: str
    query: str | None = None


class EvalRunRequest(BaseModel):
    sync_langsmith: bool = False
    dataset_path: str | None = None
    profiles_path: str | None = None
    profile_ids: list[str] | None = None


class SessionMessage(BaseModel):
    role: str
    content: str


def _resolve_model_name(request: ChatRequest) -> str:
    return request.model or get_settings().openai_model


def _allowed_file_roots_for_user(user_id: str) -> tuple[Path, ...]:
    if user_id == DEFAULT_USER_ID:
        return ALLOWED_FILE_ROOTS
    return (
        user_memory_dir(user_id),
        user_workspace_dir(user_id),
        PROJECT_ROOT / "backend" / "skills",
    )


def _resolve_user_scoped_candidate(raw_path: str, *, user_id: str) -> Path:
    raw = raw_path.strip()
    if user_id != DEFAULT_USER_ID:
        if raw.startswith("backend/memory/"):
            suffix = Path(raw).relative_to("backend/memory")
            return (user_memory_dir(user_id) / suffix).resolve()
        if raw.startswith("backend/workspace/"):
            suffix = Path(raw).relative_to("backend/workspace")
            return (user_workspace_dir(user_id) / suffix).resolve()
    return (PROJECT_ROOT / raw).resolve()


def _resolve_allowed_file_path(raw_path: str, *, user_id: str) -> Path:
    candidate = _resolve_user_scoped_candidate(raw_path, user_id=user_id)
    for root in _allowed_file_roots_for_user(user_id):
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


def _session_metadata(path: Path, *, user_id: str) -> dict[str, Any]:
    stat = path.stat()
    return {
        "name": path.stem,
        "last_modified": datetime.fromtimestamp(
            stat.st_mtime,
            tz=timezone.utc,
        ).isoformat(),
        "message_count": len(sessions_store.load_session(path.stem, user_id=user_id)),
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


def _coerce_tool_input(raw_input: Any) -> dict[str, Any]:
    if isinstance(raw_input, dict):
        return raw_input
    if isinstance(raw_input, str):
        try:
            parsed = json.loads(raw_input)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _graph_query_from_tool_call(payload: dict[str, Any]) -> str | None:
    if payload.get("name") != "search_knowledge_base":
        return None

    tool_input = _coerce_tool_input(payload.get("input"))
    if tool_input.get("use_graph") is not True:
        return None
    query = tool_input.get("query")
    return query.strip() if isinstance(query, str) and query.strip() else None


def _record_graph_retrieval(trace: dict[str, Any], query: str) -> None:
    graph_result = graph_index.expand_graph_evidence(query)
    _record_graph_result(trace, graph_result)


def _record_graph_result(trace: dict[str, Any], graph_result: dict[str, Any]) -> None:
    metadata = {
        "direct_node_ids": graph_result.get("direct_node_ids", []),
        "expanded_node_ids": graph_result.get("expanded_node_ids", []),
        "edge_types": graph_result.get("edge_types", []),
        "evidence_count": len(graph_result.get("evidence", [])),
    }
    trace["graph_retrieval"] = metadata
    traces_store.append_event(trace, kind="graph_retrieval", payload=metadata)


def _format_graph_demo_reply(query: str, graph_result: dict[str, Any]) -> str:
    if not graph_result.get("available"):
        return (
            "Graph-assisted retrieval is not available yet. Rebuild the graph with "
            "`python -m backend.graph.index`, then run this demo again."
        )

    evidence = graph_result.get("evidence", []) or []
    lines = [
        "Graph-assisted retrieval demo completed.",
        "",
        f"Query: {query}",
        "",
        "What graph expansion added:",
        f"- Direct nodes matched: {len(graph_result.get('direct_node_ids', []))}",
        f"- Expanded nodes reached: {len(graph_result.get('expanded_node_ids', []))}",
        f"- Evidence items surfaced: {len(evidence)}",
        f"- Edge types traversed: {', '.join(graph_result.get('edge_types', [])) or 'none'}",
    ]
    if evidence:
        lines.extend(["", "Evidence preview:"])
        for node in evidence[:5]:
            path = node.get("path")
            suffix = f" ({path})" if path else ""
            lines.append(
                f"- {node.get('type', 'node')}: {node.get('label', 'untitled')}{suffix}"
            )
    lines.extend(
        [
            "",
            "Interview-safe framing: this is Graph-RAG-inspired graph-assisted retrieval over local files and traces, not full community-summarization GraphRAG.",
        ]
    )
    return "\n".join(lines)


def _record_retry(trace: dict[str, Any], *, category: str, detail: str) -> None:
    trace["retry_count"] = int(trace.get("retry_count", 0)) + 1
    traces_store.append_event(
        trace,
        kind="runtime_retry",
        payload={
            "category": category,
            "detail": detail,
            "attempt": trace["retry_count"],
        },
    )


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


async def _append_session_message(session_id: str, message: dict[str, Any], *, user_id: str) -> list[dict[str, Any]]:
    return await run_with_user_lock(
        user_id,
        lambda: asyncio.to_thread(
            sessions_store.append_message,
            session_id,
            message,
            user_id=user_id,
        ),
    )


async def _write_user_file(path: Path, content: str, *, user_id: str) -> None:
    await run_with_user_lock(
        user_id,
        lambda: asyncio.to_thread(path.write_text, content, encoding="utf-8"),
    )


async def _chat_sse(request: ChatRequest, *, user_id: str) -> AsyncIterator[dict[str, str]]:
    await _append_session_message(
        request.session_id,
        {"role": "user", "content": request.message},
        user_id=user_id,
    )
    trace = traces_store.create_trace(
        session_id=request.session_id,
        model_name=_resolve_model_name(request),
        user_id=user_id,
    )
    traces_store.append_event(trace, kind="user_message", payload={"content": request.message})
    agent = build_agent(
        api_key=request.api_key,
        base_url=request.base_url,
        model_name=request.model,
    )
    payload = {"messages": sessions_store.load_session(request.session_id, user_id=user_id)}
    final_text = ""
    streamed_output_started = False
    pending_graph_query: str | None = None

    while True:
        try:
            async for event_type, event_payload in _stream_agent_events(agent, payload):
                streamed_output_started = True
                if event_type == "tool_call":
                    pending_graph_query = _graph_query_from_tool_call(event_payload)
                traces_store.append_event(trace, kind=event_type, payload=event_payload)
                if (
                    event_type == "tool_result"
                    and event_payload.get("name") == "search_knowledge_base"
                    and pending_graph_query
                ):
                    _record_graph_retrieval(trace, pending_graph_query)
                    pending_graph_query = None
                if event_type == "final":
                    final_text = _coerce_text(event_payload.get("content", ""))
                yield {
                    "event": event_type,
                    "data": json.dumps(event_payload, ensure_ascii=False),
                }
            traces_store.finalize_trace(trace, final_status="success")
            break
        except Exception as exc:
            failure = classify_runtime_failure(exc)
            traces_store.record_error(
                trace,
                category=failure.category,
                detail=failure.detail,
                friendly_message=failure.friendly_message,
                recoverable=failure.recoverable,
            )
            if should_retry_runtime_failure(
                failure,
                retry_count=int(trace.get("retry_count", 0)),
                streamed_output_started=streamed_output_started,
            ):
                _record_retry(trace, category=failure.category, detail=failure.detail)
                continue

            final_text = failure.friendly_message
            error_payload = {
                "name": "agent_error",
                "category": failure.category,
                "content": failure.friendly_message,
                "detail": failure.detail,
                "recoverable": failure.recoverable,
            }
            traces_store.append_event(trace, kind="tool_result", payload=error_payload)
            traces_store.append_event(
                trace,
                kind="final",
                payload={"content": final_text, "error_category": failure.category},
            )
            traces_store.finalize_trace(trace, final_status="error")
            yield {
                "event": "tool_result",
                "data": json.dumps(error_payload, ensure_ascii=False),
            }
            yield {
                "event": "final",
                "data": json.dumps({"content": final_text, "error_category": failure.category}, ensure_ascii=False),
            }
            break

    await _append_session_message(
        request.session_id,
        {"role": "assistant", "content": final_text},
        user_id=user_id,
    )
    traces_store.save_trace(trace)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/chat", response_model=None)
async def chat(request: ChatRequest, x_user_id: str | None = Header(default=None)) -> Any:
    user_id = normalize_user_id(x_user_id)
    if request.stream:
        return EventSourceResponse(_chat_sse(request, user_id=user_id))

    await _append_session_message(
        request.session_id,
        {"role": "user", "content": request.message},
        user_id=user_id,
    )
    trace = traces_store.create_trace(
        session_id=request.session_id,
        model_name=_resolve_model_name(request),
        user_id=user_id,
    )
    traces_store.append_event(trace, kind="user_message", payload={"content": request.message})
    agent = build_agent(
        api_key=request.api_key,
        base_url=request.base_url,
        model_name=request.model,
    )
    while True:
        try:
            result = await _invoke_agent(
                agent,
                {"messages": sessions_store.load_session(request.session_id, user_id=user_id)},
            )
            final_text = _extract_final_reply(result)
            traces_store.append_event(trace, kind="final", payload={"content": final_text})
            traces_store.finalize_trace(trace, final_status="success")
            break
        except Exception as exc:
            failure = classify_runtime_failure(exc)
            traces_store.record_error(
                trace,
                category=failure.category,
                detail=failure.detail,
                friendly_message=failure.friendly_message,
                recoverable=failure.recoverable,
            )
            if should_retry_runtime_failure(
                failure,
                retry_count=int(trace.get("retry_count", 0)),
                streamed_output_started=False,
            ):
                _record_retry(trace, category=failure.category, detail=failure.detail)
                continue

            traces_store.append_event(
                trace,
                kind="tool_result",
                payload={
                    "name": "agent_error",
                    "category": failure.category,
                    "content": failure.friendly_message,
                    "detail": failure.detail,
                    "recoverable": failure.recoverable,
                },
            )
            traces_store.finalize_trace(trace, final_status="error")
            traces_store.save_trace(trace)
            return JSONResponse(
                status_code=502,
                content=runtime_error_payload(failure, trace_id=str(trace["trace_id"])),
            )
    await _append_session_message(
        request.session_id,
        {"role": "assistant", "content": final_text},
        user_id=user_id,
    )
    traces_store.save_trace(trace)
    return {"reply": final_text, "trace_id": trace["trace_id"]}


@app.get("/api/files")
def get_file(path: str, x_user_id: str | None = Header(default=None)) -> dict[str, str]:
    user_id = normalize_user_id(x_user_id)
    resolved_path = _resolve_allowed_file_path(path, user_id=user_id)
    try:
        content = resolved_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="file not found") from exc
    return {"path": path, "content": content}


@app.post("/api/files")
async def save_file(request: FileWriteRequest, x_user_id: str | None = Header(default=None)) -> dict[str, str]:
    user_id = normalize_user_id(x_user_id)
    resolved_path = _resolve_allowed_file_path(request.path, user_id=user_id)
    await _write_user_file(resolved_path, request.content, user_id=user_id)
    return {"path": request.path, "content": request.content}


@app.get("/api/sessions")
def list_sessions(x_user_id: str | None = Header(default=None)) -> dict[str, list[dict[str, Any]]]:
    user_id = normalize_user_id(x_user_id)
    sessions_dir = sessions_store.SESSIONS_DIR if x_user_id is None else user_sessions_dir(user_id)
    if not sessions_dir.exists():
        return {"sessions": []}

    sessions = [
        _session_metadata(path, user_id=user_id)
        for path in sorted(sessions_dir.glob("*.json"))
        if path.is_file()
    ]
    return {"sessions": sessions}


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str, x_user_id: str | None = Header(default=None)) -> dict[str, Any]:
    user_id = normalize_user_id(x_user_id)
    messages = sessions_store.load_session(session_id, user_id=user_id)
    return {"session_id": session_id, "messages": messages}


@app.get("/api/traces")
def list_traces() -> dict[str, list[dict[str, Any]]]:
    if not traces_store.TRACES_DIR.exists():
        return {"traces": []}

    traces = []
    for path in sorted(traces_store.TRACES_DIR.glob("*.json"), reverse=True):
        if not path.is_file():
            continue
        trace = traces_store.load_trace(path.stem)
        if not trace:
            continue
        traces.append(
            {
                "trace_id": trace.get("trace_id"),
                "session_id": trace.get("session_id"),
                "latency_ms": trace.get("latency_ms"),
                "final_status": trace.get("final_status"),
                "error_category": trace.get("error_category"),
                "created_at": trace.get("start_time"),
            }
        )
    return {"traces": traces}


@app.get("/api/traces/{trace_id}")
def get_trace(trace_id: str) -> dict[str, Any]:
    trace = traces_store.load_trace(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="trace not found")
    return trace


@app.get("/api/graph")
def get_graph_summary() -> dict[str, Any]:
    graph = graph_index.load_graph()
    if graph is None:
        return {
            "available": False,
            "summary": {
                "schema_version": None,
                "node_count": 0,
                "edge_count": 0,
                "node_counts": {},
                "edge_counts": {},
                "sources": {},
            },
        }
    return {"available": True, "summary": graph_index.graph_summary(graph)}


@app.get("/api/graph/nodes/{node_id}")
def get_graph_node(node_id: str) -> dict[str, Any]:
    graph = graph_index.load_graph()
    if graph is None:
        raise HTTPException(status_code=404, detail="graph not found")
    for node in graph.get("nodes", []):
        if node.get("id") == node_id:
            edges = [
                edge
                for edge in graph.get("edges", [])
                if edge.get("source") == node_id or edge.get("target") == node_id
            ]
            return {"node": node, "edges": edges}
    raise HTTPException(status_code=404, detail="graph node not found")


@app.post("/api/graph/demo")
async def run_graph_demo(
    request: GraphDemoRequest,
    x_user_id: str | None = Header(default=None),
) -> dict[str, str]:
    user_id = normalize_user_id(x_user_id)
    query = (
        request.query
        or "Mini-OpenClaw eval notes interview demo skills runtime diagnostics"
    )
    await _append_session_message(
        request.session_id,
        {"role": "user", "content": request.message},
        user_id=user_id,
    )
    trace = traces_store.create_trace(
        session_id=request.session_id,
        model_name="graph-demo-local",
        user_id=user_id,
    )
    traces_store.append_event(trace, kind="user_message", payload={"content": request.message})
    traces_store.append_event(
        trace,
        kind="tool_call",
        payload={
            "name": "search_knowledge_base",
            "input": {"query": query, "use_graph": True},
        },
    )
    graph_result = graph_index.expand_graph_evidence(query)
    _record_graph_result(trace, graph_result)
    reply = _format_graph_demo_reply(query, graph_result)
    traces_store.append_event(
        trace,
        kind="tool_result",
        payload={
            "name": "search_knowledge_base",
            "content": reply,
        },
    )
    traces_store.append_event(trace, kind="final", payload={"content": reply})
    traces_store.finalize_trace(trace, final_status="success")
    traces_store.save_trace(trace)
    await _append_session_message(
        request.session_id,
        {"role": "assistant", "content": reply},
        user_id=user_id,
    )
    return {"reply": reply, "trace_id": str(trace["trace_id"])}


@app.post("/api/evals/run")
async def run_evals(request: EvalRunRequest) -> dict[str, Any]:
    return submit_eval_job(
        dataset_path=request.dataset_path or DEFAULT_DATASET_PATH,
        profiles_path=request.profiles_path or DEFAULT_PROFILES_PATH,
        profile_ids=request.profile_ids,
        sync_langsmith=request.sync_langsmith,
    )


@app.get("/api/evals/jobs/{job_id}")
def get_eval_job_status(job_id: str) -> dict[str, Any]:
    job = get_eval_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="eval job not found")
    return job


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "backend.app:app",
        host=settings.backend_host,
        port=settings.backend_port,
        reload=False,
    )
