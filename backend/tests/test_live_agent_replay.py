from __future__ import annotations

import unittest
from collections.abc import AsyncIterator

from backend.evals.live_agent_replay import run_live_agent_replay
from backend.evals.runner import EvaluationTask


async def _successful_stream(*_: object) -> AsyncIterator[dict[str, str]]:
    yield {"event": "tool_call", "data": '{"name":"read_file"}'}
    yield {"event": "tool_result", "data": '{"name":"read_file","content":"ok"}'}
    yield {"event": "final", "data": '{"content":"completed"}'}


async def _missing_tool_stream(*_: object) -> AsyncIterator[dict[str, str]]:
    yield {"event": "final", "data": '{"content":"completed"}'}


class LiveAgentReplayTests(unittest.TestCase):
    def test_reports_real_stream_contract_signals(self) -> None:
        tasks = [
            EvaluationTask("read", "file_reading", "read", "expected", [], ["read_file"]),
            EvaluationTask("chat", "multi_turn_context", "chat", "expected", [], []),
        ]

        report = run_live_agent_replay(tasks, stream_runner=_successful_stream)

        self.assertEqual(report["execution_mode"], "live_product_agent_replay")
        self.assertEqual(report["metrics"]["task_contract_pass_rate"], 1.0)
        self.assertEqual(report["metrics"]["required_tool_coverage_rate"], 1.0)
        self.assertEqual(report["results"][0]["observed_tools"], ["read_file"])

    def test_missing_required_tool_fails_contract_without_claiming_agent_error(self) -> None:
        task = EvaluationTask("read", "file_reading", "read", "expected", [], ["read_file"])

        report = run_live_agent_replay([task], stream_runner=_missing_tool_stream)

        self.assertEqual(report["metrics"]["response_completion_rate"], 1.0)
        self.assertEqual(report["metrics"]["task_contract_pass_rate"], 0.0)
        self.assertEqual(report["results"][0]["missing_required_tools"], ["read_file"])


if __name__ == "__main__":
    unittest.main()
