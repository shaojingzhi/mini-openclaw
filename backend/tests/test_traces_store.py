"""Unit tests for backend.traces_store."""

from __future__ import annotations

import importlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

tr_mod = importlib.import_module("backend.traces_store")


class TracesStoreTests(unittest.TestCase):
    def test_save_and_load_trace_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            traces_dir = Path(tmp)
            with patch.object(tr_mod, "TRACES_DIR", traces_dir):
                trace = tr_mod.create_trace(session_id="main", model_name="gpt-5.4")
                tr_mod.append_event(trace, kind="tool_call", payload={"name": "read_file"})
                tr_mod.finalize_trace(trace, final_status="success")
                saved = tr_mod.save_trace(trace)
                loaded = tr_mod.load_trace(trace["trace_id"])
                self.assertTrue(saved.exists())
                self.assertIsNotNone(loaded)
                assert loaded is not None
                self.assertEqual(loaded["session_id"], "main")
                self.assertEqual(loaded["model_name"], "gpt-5.4")
                self.assertEqual(loaded["final_status"], "success")
                self.assertEqual(len(loaded["tool_calls"]), 1)
                self.assertGreaterEqual(loaded["latency_ms"], 0.0)

    def test_error_tool_result_is_counted_as_failure(self) -> None:
        trace = tr_mod.create_trace(session_id="main", model_name="gpt-5.4")
        tr_mod.append_event(
            trace,
            kind="tool_result",
            payload={"name": "agent_error", "content": "boom"},
        )
        self.assertEqual(len(trace["tool_failures"]), 1)

    def test_record_error_sets_top_level_fields(self) -> None:
        trace = tr_mod.create_trace(session_id="main", model_name="gpt-5.4")
        tr_mod.record_error(
            trace,
            category="tool_timeout",
            detail="tool timed out",
            friendly_message="A local tool timed out before it could finish. Please try again.",
            recoverable=True,
        )
        self.assertEqual(trace["error_category"], "tool_timeout")
        self.assertEqual(trace["error_message"], "tool timed out")
        self.assertTrue(trace["recoverable"])


if __name__ == "__main__":
    unittest.main()
