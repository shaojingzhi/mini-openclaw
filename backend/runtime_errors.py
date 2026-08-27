"""Runtime error classification and recovery helpers."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RuntimeFailure:
    category: str
    detail: str
    friendly_message: str
    recoverable: bool


_RETRYABLE_CATEGORIES = {
    "tool_timeout",
    "model_invalid_format",
    "knowledge_retrieval_failure",
}


_SENSITIVE_VALUE_PATTERN = re.compile(
    r"(?i)\b(api[_ -]?key)\b\s*[:=]\s*(?:\"[^\"]*\"|'[^']*'|[^\s,;}\]]+)"
)
_AUTHORIZATION_VALUE_PATTERN = re.compile(
    r"(?i)\b(authorization)\b\s*[:=]\s*(?:\"[^\"]*\"|'[^']*'|[^\s,;}\]]+(?:\s+[^\s,;}\]]+)*)"
)
_BEARER_TOKEN_PATTERN = re.compile(r"(?i)\bbearer\s+[^\s,;}\]]+")
_TOOL_CALL_MARKERS = ("tool_call_id", "tool call id", "tool_calls", "tool call", "function call", "arguments")


def sanitize_error_text(value: Exception | str) -> str:
    """Redact credentials before an error can enter traces or API responses."""
    text = str(value).strip() or value.__class__.__name__
    text = _AUTHORIZATION_VALUE_PATTERN.sub(lambda match: f"{match.group(1)}=[redacted]", text)
    text = _BEARER_TOKEN_PATTERN.sub("Bearer [redacted]", text)
    text = _SENSITIVE_VALUE_PATTERN.sub(r"\1=[redacted]", text)
    return text


def provider_tool_call_diagnostic(error: Exception) -> str | None:
    """Return a bounded, redacted reason only for malformed provider tool calls."""
    detail = sanitize_error_text(error)
    lowered = detail.lower()
    has_marker = any(marker in lowered for marker in _TOOL_CALL_MARKERS)
    is_malformed = any(marker in lowered for marker in ("missing", "empty", "invalid", "unexpected", "required"))
    if not (has_marker and is_malformed):
        return None
    return detail[:800]


def classify_runtime_failure(error: Exception) -> RuntimeFailure:
    detail = sanitize_error_text(error)
    lowered = detail.lower()

    if provider_tool_call_diagnostic(error) is not None:
        return RuntimeFailure(
            category="provider_tool_call_invalid",
            detail=detail,
            friendly_message=(
                "The current model or gateway did not return a standard function/tool call, "
                "so no memory proposal was created. Use a provider that supports OpenAI-compatible tool calling."
            ),
            recoverable=False,
        )

    if (
        "401" in lowered
        or "unauthorized" in lowered
        or "invalid api key" in lowered
        or "incorrect api key" in lowered
        or "expired" in lowered
        or "令牌已过期" in detail
        or ("token" in lowered and "expired" in lowered)
    ):
        return RuntimeFailure(
            category="model_auth_error",
            detail=detail,
            friendly_message=(
                "The model API key is invalid or expired. Clear the local API key "
                "in Request settings or enter a valid key, then try again."
            ),
            recoverable=False,
        )

    if isinstance(error, TimeoutError) or "timeout" in lowered or "timed out" in lowered:
        return RuntimeFailure(
            category="tool_timeout",
            detail=detail,
            friendly_message="A local tool timed out before it could finish. Please try again.",
            recoverable=True,
        )

    if "max iterations" in lowered or "maximum iterations" in lowered or "recursion limit" in lowered:
        return RuntimeFailure(
            category="max_iterations_exceeded",
            detail=detail,
            friendly_message="The assistant hit its step limit before finishing. Try narrowing the request.",
            recoverable=False,
        )

    if "knowledge" in lowered or "retriev" in lowered or "embedding" in lowered or "vector" in lowered or "bm25" in lowered:
        return RuntimeFailure(
            category="knowledge_retrieval_failure",
            detail=detail,
            friendly_message="Knowledge retrieval is temporarily unavailable, so the answer may be incomplete right now.",
            recoverable=True,
        )

    if "memory" in lowered and ("read" in lowered or "load" in lowered or "open" in lowered or "file" in lowered):
        return RuntimeFailure(
            category="memory_read_failure",
            detail=detail,
            friendly_message="I could not read the local memory files just now. Please try again.",
            recoverable=True,
        )

    if isinstance(error, json.JSONDecodeError) or "invalid format" in lowered or "malformed json" in lowered or "parse error" in lowered or "structured output" in lowered:
        return RuntimeFailure(
            category="model_invalid_format",
            detail=detail,
            friendly_message="The model returned an unexpected response format. Please retry the request.",
            recoverable=True,
        )

    if isinstance(error, (TypeError, ValueError)) or "invalid input" in lowered or "missing required" in lowered or "schema" in lowered or "empty string" in lowered:
        return RuntimeFailure(
            category="tool_invalid_input",
            detail=detail,
            friendly_message="One of the tool inputs was invalid. Please revise the request and try again.",
            recoverable=False,
        )

    return RuntimeFailure(
        category="model_invalid_format",
        detail=detail,
        friendly_message="The assistant returned an unexpected response format. Please retry the request.",
        recoverable=True,
    )


def should_retry_runtime_failure(
    failure: RuntimeFailure,
    *,
    retry_count: int,
    streamed_output_started: bool,
) -> bool:
    return (
        failure.recoverable
        and not streamed_output_started
        and retry_count < 1
        and failure.category in _RETRYABLE_CATEGORIES
    )


def runtime_error_payload(failure: RuntimeFailure, *, trace_id: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "error_category": failure.category,
        "detail": failure.friendly_message,
        "error_message": sanitize_error_text(failure.detail),
        "friendly_message": failure.friendly_message,
        "recoverable": failure.recoverable,
    }
    if trace_id is not None:
        payload["trace_id"] = trace_id
    return payload


__all__ = [
    "RuntimeFailure",
    "classify_runtime_failure",
    "provider_tool_call_diagnostic",
    "runtime_error_payload",
    "sanitize_error_text",
    "should_retry_runtime_failure",
]
