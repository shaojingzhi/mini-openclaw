"""Unit tests for runtime error classification helpers."""

from __future__ import annotations

import importlib
import json
import unittest

rt_mod = importlib.import_module("backend.runtime_errors")


class RuntimeErrorClassificationTests(unittest.TestCase):
    def test_classifies_tool_timeout(self) -> None:
        failure = rt_mod.classify_runtime_failure(TimeoutError("tool timed out while reading file"))
        self.assertEqual(failure.category, "tool_timeout")
        self.assertTrue(failure.recoverable)

    def test_classifies_tool_invalid_input(self) -> None:
        failure = rt_mod.classify_runtime_failure(ValueError("invalid input: path is required"))
        self.assertEqual(failure.category, "tool_invalid_input")
        self.assertFalse(failure.recoverable)

    def test_classifies_model_invalid_format(self) -> None:
        failure = rt_mod.classify_runtime_failure(json.JSONDecodeError("bad json", "x", 0))
        self.assertEqual(failure.category, "model_invalid_format")
        self.assertTrue(failure.recoverable)

    def test_classifies_expired_api_key_as_auth_error(self) -> None:
        failure = rt_mod.classify_runtime_failure(
            RuntimeError(
                "Error code: 401 - {'error': {'message': '该令牌已过期'}}"
            )
        )
        self.assertEqual(failure.category, "model_auth_error")
        self.assertFalse(failure.recoverable)
        self.assertIn("API key", failure.friendly_message)

    def test_classifies_memory_read_failure(self) -> None:
        failure = rt_mod.classify_runtime_failure(RuntimeError("memory read failed: permission denied"))
        self.assertEqual(failure.category, "memory_read_failure")

    def test_classifies_knowledge_retrieval_failure(self) -> None:
        failure = rt_mod.classify_runtime_failure(RuntimeError("knowledge retrieval failed: vector index missing"))
        self.assertEqual(failure.category, "knowledge_retrieval_failure")
        self.assertTrue(failure.recoverable)

    def test_classifies_max_iterations_exceeded(self) -> None:
        failure = rt_mod.classify_runtime_failure(RuntimeError("max iterations exceeded in graph runner"))
        self.assertEqual(failure.category, "max_iterations_exceeded")
        self.assertFalse(failure.recoverable)

    def test_classifies_and_redacts_malformed_provider_tool_call(self) -> None:
        error = ValueError("ToolMessage missing tool_call_id; api_key=secret-token arguments={}")
        failure = rt_mod.classify_runtime_failure(error)
        diagnostic = rt_mod.provider_tool_call_diagnostic(error)

        self.assertEqual(failure.category, "provider_tool_call_invalid")
        self.assertIn("no memory proposal was created", failure.friendly_message)
        self.assertNotIn("secret-token", failure.detail)
        self.assertIsNotNone(diagnostic)
        self.assertNotIn("secret-token", diagnostic or "")
        self.assertNotIn("secret-token", rt_mod.runtime_error_payload(failure)["error_message"])

    def test_redacts_authorization_bearer_forms_completely(self) -> None:
        cases = (
            "Authorization: Bearer secret-token",
            "authorization=Bearer secret-token",
            "Authorization: Basic secret-token",
            "authorization=Token secret-token",
            'Authorization: "Basic secret-token"',
            "Bearer secret-token",
            "api_key='secret-token'",
            'api_key="secret-token"',
        )

        for raw in cases:
            with self.subTest(raw=raw):
                self.assertNotIn("secret-token", rt_mod.sanitize_error_text(raw))
                failure = rt_mod.classify_runtime_failure(ValueError(raw))
                self.assertNotIn("secret-token", failure.detail)
                self.assertNotIn("secret-token", rt_mod.runtime_error_payload(failure)["error_message"])

        self.assertEqual(
            rt_mod.sanitize_error_text("Authorization: Bearer secret-token"),
            "Authorization=[redacted]",
        )

    def test_retries_only_retryable_categories_before_output(self) -> None:
        failure = rt_mod.classify_runtime_failure(TimeoutError("tool timeout"))
        self.assertTrue(rt_mod.should_retry_runtime_failure(failure, retry_count=0, streamed_output_started=False))
        self.assertFalse(rt_mod.should_retry_runtime_failure(failure, retry_count=1, streamed_output_started=False))
        self.assertFalse(rt_mod.should_retry_runtime_failure(failure, retry_count=0, streamed_output_started=True))
        auth_failure = rt_mod.classify_runtime_failure(RuntimeError("401 token expired"))
        self.assertFalse(rt_mod.should_retry_runtime_failure(auth_failure, retry_count=0, streamed_output_started=False))


if __name__ == "__main__":
    unittest.main()
