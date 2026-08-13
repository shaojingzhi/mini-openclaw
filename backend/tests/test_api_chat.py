"""Integration tests for the /api/chat endpoint."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

app_mod = importlib.import_module("backend.app")
ss_mod = importlib.import_module("backend.sessions_store")
tr_mod = importlib.import_module("backend.traces_store")
us_mod = importlib.import_module("backend.user_state")
ps_mod = importlib.import_module("backend.memory.proposals_store")


class _StreamingAgent:
    def __init__(self) -> None:
        self.payloads: list[dict[str, object]] = []

    async def astream_events(self, payload, version="v2"):
        self.payloads.append(payload)
        yield {"type": "thought", "data": {"content": "thinking"}}
        yield {
            "type": "tool_call",
            "data": {"name": "python_repl", "input": {"query": "print(2 + 2)"}},
        }
        yield {
            "type": "tool_result",
            "data": {"name": "python_repl", "content": "4"},
        }
        yield {"type": "final", "data": {"content": "hello back"}}


class _GraphStreamingAgent:
    async def astream_events(self, payload, version="v2"):
        yield {"type": "thought", "data": {"content": "graph thinking"}}
        yield {
            "type": "tool_call",
            "data": {
                "name": "search_knowledge_base",
                "input": {
                    "query": "connect eval notes to interview demo",
                    "use_graph": True,
                },
            },
        }
        yield {
            "type": "tool_result",
            "data": {
                "name": "search_knowledge_base",
                "content": "Direct matches:\n...\n\nGraph-expanded evidence:\n...",
            },
        }
        yield {"type": "final", "data": {"content": "graph answer"}}


class _InvokeAgent:
    def __init__(self, reply: str = "plain reply") -> None:
        self.payloads: list[dict[str, object]] = []
        self.reply = reply

    async def ainvoke(self, payload):
        self.payloads.append(payload)
        return {"messages": [{"role": "assistant", "content": self.reply}]}


class _EvidenceInvokeAgent(_InvokeAgent):
    def __init__(self, reply: str, evidence: str) -> None:
        super().__init__(reply)
        self.evidence = evidence

    async def ainvoke(self, payload):
        self.payloads.append(payload)
        return {
            "messages": [
                {
                    "role": "tool",
                    "name": "search_knowledge_base",
                    "content": self.evidence,
                },
                {"role": "assistant", "content": self.reply},
            ]
        }


class _FinalStreamingAgent:
    def __init__(self, reply: str, evidence: str | None = None) -> None:
        self.reply = reply
        self.evidence = evidence
        self.payloads: list[dict[str, object]] = []

    async def astream_events(self, payload, version="v2"):
        self.payloads.append(payload)
        if self.evidence is not None:
            yield {
                "type": "tool_result",
                "data": {
                    "name": "search_knowledge_base",
                    "content": self.evidence,
                },
            }
        yield {"type": "final", "data": {"content": self.reply}}


class _FlakyRecoverableAgent:
    def __init__(self) -> None:
        self.calls = 0

    async def ainvoke(self, payload):
        self.calls += 1
        if self.calls == 1:
            raise TimeoutError("tool timed out while fetching data")
        return {"messages": [{"role": "assistant", "content": "recovered reply"}]}


class ApiChatTests(unittest.TestCase):
    def test_streaming_chat_emits_sse_events_and_persists_messages(self) -> None:
        agent = _StreamingAgent()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            traces_dir = tmp_path / "traces"
            data_users_dir = tmp_path / "users"
            with patch.object(ss_mod, "SESSIONS_DIR", tmp_path), patch.object(us_mod, "DATA_USERS_DIR", data_users_dir), patch.object(tr_mod, "TRACES_DIR", traces_dir), patch.object(
                app_mod, "build_agent", return_value=agent
            ):
                client = TestClient(app_mod.app)
                response = client.post(
                    "/api/chat",
                    json={"message": "say hello", "session_id": "main", "stream": True},
                )
                persisted = ss_mod.load_session("main", user_id="anonymous")
                trace_files = list(traces_dir.glob("*.json"))
                trace = json.loads(trace_files[0].read_text(encoding="utf-8"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "text/event-stream; charset=utf-8")
        body = response.text
        self.assertIn("event: thought", body)
        self.assertIn('data: {"content": "thinking", "agent_id": "lighthouse"}', body)
        self.assertIn("event: tool_call", body)
        self.assertIn("event: tool_result", body)
        self.assertIn("event: final", body)
        self.assertIn('data: {"content": "hello back", "agent_id": "lighthouse"}', body)
        self.assertGreaterEqual(body.count('"agent_id": "lighthouse"'), 5)
        self.assertEqual(
            agent.payloads,
            [{"messages": [{"role": "user", "content": "say hello"}]}],
        )
        self.assertEqual(persisted[0], {"role": "user", "content": "say hello"})
        self.assertEqual(persisted[1]["role"], "assistant")
        self.assertEqual(persisted[1]["content"], "hello back")
        self.assertEqual(persisted[1]["author_agent_id"], "lighthouse")
        self.assertEqual(persisted[1]["visibility"], "user")
        self.assertEqual(trace["session_id"], "main")
        self.assertEqual(trace["selected_agent_id"], "lighthouse")
        self.assertEqual(trace["final_status"], "success")
        self.assertEqual(trace["model_name"], os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
        self.assertEqual(len(trace["tool_calls"]), 1)
        self.assertEqual(len(trace["events"]), 7)
        self.assertEqual(trace["events"][1]["kind"], "agent_routed")
        self.assertEqual(trace["events"][2]["kind"], "memory_loaded")
        self.assertEqual(trace["events"][2]["payload"]["memory_count"], 0)

    def test_streaming_graph_search_records_trace_metadata(self) -> None:
        agent = _GraphStreamingAgent()
        graph_result = {
            "available": True,
            "direct_node_ids": ["document:eval"],
            "expanded_node_ids": ["workspace:demo", "trace:last"],
            "edge_types": ["mentions", "contains"],
            "evidence": [{"id": "document:eval"}, {"id": "workspace:demo"}],
        }
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            traces_dir = tmp_path / "traces"
            data_users_dir = tmp_path / "users"
            with patch.object(ss_mod, "SESSIONS_DIR", tmp_path), patch.object(us_mod, "DATA_USERS_DIR", data_users_dir), patch.object(tr_mod, "TRACES_DIR", traces_dir), patch.object(
                app_mod, "build_agent", return_value=agent
            ), patch.object(app_mod.graph_index, "expand_graph_evidence", return_value=graph_result) as expand_graph:
                client = TestClient(app_mod.app)
                response = client.post(
                    "/api/chat",
                    json={"message": "run graph demo", "session_id": "main", "stream": True},
                )
                trace_files = list(traces_dir.glob("*.json"))
                trace = json.loads(trace_files[0].read_text(encoding="utf-8"))

        self.assertEqual(response.status_code, 200)
        expand_graph.assert_called_once_with("connect eval notes to interview demo")
        self.assertEqual(
            trace["graph_retrieval"],
            {
                "direct_node_ids": ["document:eval"],
                "expanded_node_ids": ["workspace:demo", "trace:last"],
                "edge_types": ["mentions", "contains"],
                "evidence_count": 2,
            },
        )
        self.assertEqual(trace["events"][-2]["kind"], "graph_retrieval")
        self.assertIn("Graph-expanded evidence", response.text)

    def test_non_streaming_chat_returns_json_and_persists_messages(self) -> None:
        agent = _InvokeAgent()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            traces_dir = tmp_path / "traces"
            data_users_dir = tmp_path / "users"
            with patch.object(ss_mod, "SESSIONS_DIR", tmp_path), patch.object(us_mod, "DATA_USERS_DIR", data_users_dir), patch.object(tr_mod, "TRACES_DIR", traces_dir), patch.object(
                app_mod, "build_agent", return_value=agent
            ):
                client = TestClient(app_mod.app)
                response = client.post(
                    "/api/chat",
                    json={"message": "say hello", "session_id": "main", "stream": False},
                )
                persisted = ss_mod.load_session("main", user_id="anonymous")
                trace_files = list(traces_dir.glob("*.json"))
                trace = json.loads(trace_files[0].read_text(encoding="utf-8"))

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["reply"], "plain reply")
        self.assertTrue(body["trace_id"].startswith("trace_"))
        self.assertEqual(
            agent.payloads,
            [{"messages": [{"role": "user", "content": "say hello"}]}],
        )
        self.assertEqual(persisted[0], {"role": "user", "content": "say hello"})
        self.assertEqual(persisted[1]["content"], "plain reply")
        self.assertEqual(persisted[1]["author_agent_id"], "lighthouse")
        self.assertEqual(body["agent"]["agent_id"], "lighthouse")
        self.assertEqual(trace["final_status"], "success")
        self.assertEqual(trace["events"][-1]["kind"], "final")

    def test_explicit_mention_routes_to_spark_and_filters_private_memory(self) -> None:
        agent = _InvokeAgent("spark reply")
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            traces_dir = tmp_path / "traces"
            data_users_dir = tmp_path / "users"
            memory_dir = tmp_path / "memory"
            with patch.object(ss_mod, "SESSIONS_DIR", tmp_path / "sessions"), patch.object(
                us_mod, "DATA_USERS_DIR", data_users_dir
            ), patch.object(tr_mod, "TRACES_DIR", traces_dir), patch.object(
                ps_mod, "MEMORY_DIR", memory_dir
            ):
                proposals = []
                for target, owner, content in (
                    ("project_memory", "lighthouse", "Shared project fact."),
                    ("relationship_memory", "spark", "Spark private preference."),
                    ("relationship_memory", "whetstone", "Whetstone private preference."),
                ):
                    proposal, _ = ps_mod.create_proposal(
                        user_id="alice",
                        session_id="main",
                        agent_id=owner,
                        target=target,
                        memory_type="behavior_preference",
                        content=content,
                        rationale="Test memory boundary.",
                    )
                    ps_mod.decide_proposal(
                        user_id="alice", proposal_id=proposal["proposal_id"], decision="approved"
                    )
                    proposals.append(proposal)
                build_args: dict[str, object] = {}

                def capture_build(**kwargs):
                    build_args.update(kwargs)
                    return agent

                with patch.object(app_mod, "build_agent", side_effect=capture_build):
                    client = TestClient(app_mod.app)
                    response = client.post(
                        "/api/chat",
                        headers={"X-User-ID": "alice"},
                        json={"message": "@火花 给我两个方案", "session_id": "main", "stream": False},
                    )
                trace = json.loads(next(traces_dir.glob("*.json")).read_text(encoding="utf-8"))

        loaded_ids = {memory["proposal_id"] for memory in build_args["approved_memories"]}
        self.assertEqual(build_args["agent_profile"].agent_id, "spark")
        self.assertEqual(loaded_ids, {proposals[0]["proposal_id"], proposals[1]["proposal_id"]})
        self.assertEqual(response.json()["agent"]["agent_id"], "spark")
        self.assertEqual(trace["events"][1]["payload"]["route_reason"], "explicit_mention")

    def test_non_streaming_handoff_invokes_target_once_and_persists_provenance(self) -> None:
        built_agents: list[str] = []
        source_agent = _EvidenceInvokeAgent(
            "host draft",
            "verified evidence " + ("x" * 1_200),
        )
        target_agent = _InvokeAgent("calibrated answer")

        def build_with_handoff(**kwargs):
            agent_id = kwargs["agent_profile"].agent_id
            built_agents.append(agent_id)
            if agent_id == "lighthouse":
                kwargs["on_handoff_requested"](
                    {
                        "from_agent_id": "lighthouse",
                        "to_agent_id": "whetstone",
                        "task": "Validate the interview claim.",
                        "reason": "This claim needs a stricter risk check.",
                    }
                )
                return source_agent
            return target_agent

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            traces_dir = tmp_path / "traces"
            data_users_dir = tmp_path / "users"
            with patch.object(ss_mod, "SESSIONS_DIR", tmp_path), patch.object(
                us_mod, "DATA_USERS_DIR", data_users_dir
            ), patch.object(tr_mod, "TRACES_DIR", traces_dir), patch.object(
                app_mod, "build_agent", side_effect=build_with_handoff
            ):
                client = TestClient(app_mod.app)
                response = client.post(
                    "/api/chat",
                    json={"message": "Review this claim", "session_id": "main", "stream": False},
                )
                persisted = ss_mod.load_session("main", user_id="anonymous")
                trace = json.loads(next(traces_dir.glob("*.json")).read_text(encoding="utf-8"))

        self.assertEqual(built_agents, ["lighthouse", "whetstone"])
        self.assertEqual(response.json()["reply"], "calibrated answer")
        self.assertEqual(response.json()["agent"]["agent_id"], "whetstone")
        self.assertEqual(persisted[-1]["author_agent_id"], "whetstone")
        self.assertEqual(persisted[-1]["handoff_from_agent_id"], "lighthouse")
        target_messages = target_agent.payloads[0]["messages"]
        self.assertEqual(target_messages[0]["role"], "system")
        self.assertEqual(target_messages[-1], {"role": "user", "content": "Review this claim"})
        self.assertEqual(
            [message["role"] for message in target_messages].count("user"),
            1,
        )
        self.assertIn("not a user message", target_messages[0]["content"])
        envelope = json.loads(target_messages[0]["content"].splitlines()[-1])
        self.assertEqual(envelope["evidence"][0]["tool_name"], "search_knowledge_base")
        self.assertEqual(len(envelope["evidence"][0]["content"]), 1_000)
        handoff_id = response.json()["handoff"]["handoff_id"]
        requested_event = next(
            event for event in trace["events"] if event["kind"] == "handoff_requested"
        )
        self.assertEqual(envelope["handoff_id"], handoff_id)
        self.assertEqual(persisted[-1]["handoff_id"], handoff_id)
        self.assertEqual(trace["last_handoff_id"], handoff_id)
        self.assertEqual(requested_event["payload"]["handoff_id"], handoff_id)
        self.assertEqual(requested_event["payload"]["evidence_count"], 1)
        self.assertEqual(trace["handoff_count"], 1)
        self.assertIn("handoff_requested", [event["kind"] for event in trace["events"]])
        self.assertIn("handoff_completed", [event["kind"] for event in trace["events"]])

    def test_streaming_handoff_hides_host_draft(self) -> None:
        source_agent = _FinalStreamingAgent("host draft", "verified streaming evidence")
        target_agent = _FinalStreamingAgent("scout answer")

        def build_with_handoff(**kwargs):
            if kwargs["agent_profile"].agent_id == "lighthouse":
                kwargs["on_handoff_requested"](
                    {
                        "from_agent_id": "lighthouse",
                        "to_agent_id": "spark",
                        "task": "Explore alternatives.",
                        "reason": "The user would benefit from a broader option set.",
                    }
                )
                return source_agent
            return target_agent

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            traces_dir = tmp_path / "traces"
            with patch.object(ss_mod, "SESSIONS_DIR", tmp_path), patch.object(
                us_mod, "DATA_USERS_DIR", tmp_path / "users"
            ), patch.object(tr_mod, "TRACES_DIR", traces_dir), patch.object(
                app_mod, "build_agent", side_effect=build_with_handoff
            ):
                client = TestClient(app_mod.app)
                response = client.post(
                    "/api/chat",
                    json={"message": "Find options", "session_id": "main", "stream": True},
                )
                persisted = ss_mod.load_session("main", user_id="anonymous")
                trace = json.loads(next(traces_dir.glob("*.json")).read_text(encoding="utf-8"))

        self.assertIn("event: handoff", response.text)
        self.assertIn('"evidence_count": 1', response.text)
        self.assertNotIn("host draft", response.text)
        self.assertIn("scout answer", response.text)
        self.assertEqual(persisted[-1]["content"], "scout answer")
        self.assertEqual(persisted[-1]["author_agent_id"], "spark")
        target_messages = target_agent.payloads[0]["messages"]
        self.assertEqual(target_messages[0]["role"], "system")
        self.assertEqual(target_messages[-1], {"role": "user", "content": "Find options"})
        envelope = json.loads(target_messages[0]["content"].splitlines()[-1])
        self.assertEqual(
            envelope["evidence"],
            [
                {
                    "tool_name": "search_knowledge_base",
                    "content": "verified streaming evidence",
                    "visibility": "shared",
                }
            ],
        )
        handoff_id = persisted[-1]["handoff_id"]
        self.assertEqual(envelope["handoff_id"], handoff_id)
        self.assertEqual(trace["last_handoff_id"], handoff_id)

    def test_handoff_excludes_private_tool_evidence(self) -> None:
        handoff = app_mod._prepare_handoff(
            {
                "from_agent_id": "lighthouse",
                "to_agent_id": "spark",
                "task": "Compare the public evidence.",
                "reason": "A second perspective is useful.",
            },
            [
                app_mod._tool_evidence(
                    tool_name="read_file",
                    content="Private Whetstone memory.",
                ),
                app_mod._tool_evidence(
                    tool_name="search_knowledge_base",
                    content="Shared knowledge evidence.",
                ),
            ],
        )

        self.assertEqual(
            handoff["evidence"],
            [
                {
                    "tool_name": "search_knowledge_base",
                    "content": "Shared knowledge evidence.",
                    "visibility": "shared",
                }
            ],
        )

    def test_chat_loads_approved_memory_and_records_created_proposal(self) -> None:
        agent = _InvokeAgent()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            traces_dir = tmp_path / "traces"
            data_users_dir = tmp_path / "users"
            with patch.object(ss_mod, "SESSIONS_DIR", tmp_path / "sessions"), patch.object(
                us_mod, "DATA_USERS_DIR", data_users_dir
            ), patch.object(tr_mod, "TRACES_DIR", traces_dir), patch.object(
                ps_mod, "MEMORY_DIR", tmp_path / "memory"
            ):
                approved, _ = ps_mod.create_proposal(
                    user_id="alice",
                    session_id="main",
                    target="user_capsule",
                    memory_type="user_preference",
                    content="Use Chinese for interview answers.",
                    rationale="The user explicitly asked for it.",
                )
                ps_mod.decide_proposal(
                    user_id="alice", proposal_id=approved["proposal_id"], decision="approved"
                )
                created, _ = ps_mod.create_proposal(
                    user_id="alice",
                    session_id="main",
                    target="project_memory",
                    memory_type="task_state",
                    content="Review the pending deployment checklist next.",
                    rationale="The user explicitly asked to retain the task state.",
                )
                build_args: dict[str, object] = {}

                def build_with_proposal(**kwargs):
                    build_args.update(kwargs)
                    kwargs["on_memory_proposal_created"](created)
                    return agent

                with patch.object(app_mod, "build_agent", side_effect=build_with_proposal):
                    client = TestClient(app_mod.app)
                    response = client.post(
                        "/api/chat",
                        headers={"X-User-ID": "alice"},
                        json={"message": "hello", "session_id": "main", "stream": False},
                    )
                trace = json.loads(next(traces_dir.glob("*.json")).read_text(encoding="utf-8"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [memory["proposal_id"] for memory in build_args["approved_memories"]],
            [approved["proposal_id"]],
        )
        events_by_kind = {event["kind"]: event["payload"] for event in trace["events"]}
        self.assertEqual(events_by_kind["memory_loaded"]["memory_count"], 1)
        self.assertEqual(events_by_kind["memory_loaded"]["approved_total"], 1)
        self.assertEqual(events_by_kind["memory_loaded"]["omitted_proposal_ids"], [])
        self.assertEqual(events_by_kind["memory_loaded"]["layer_counts"], {"user_capsule": 1})
        self.assertEqual(events_by_kind["memory_loaded"]["proposal_ids"], [approved["proposal_id"]])
        self.assertEqual(
            events_by_kind["memory_proposal_created"]["proposal_id"], created["proposal_id"]
        )

    def test_non_streaming_chat_failure_returns_categorized_payload(self) -> None:
        class _FailingAgent:
            async def ainvoke(self, payload):
                raise RuntimeError("provider timeout")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            traces_dir = tmp_path / "traces"
            data_users_dir = tmp_path / "users"
            with patch.object(ss_mod, "SESSIONS_DIR", tmp_path), patch.object(us_mod, "DATA_USERS_DIR", data_users_dir), patch.object(tr_mod, "TRACES_DIR", traces_dir), patch.object(
                app_mod, "build_agent", return_value=_FailingAgent()
            ):
                client = TestClient(app_mod.app)
                response = client.post(
                    "/api/chat",
                    json={"message": "say hello", "session_id": "main", "stream": False},
                )
                trace_files = list(traces_dir.glob("*.json"))
                trace = json.loads(trace_files[0].read_text(encoding="utf-8"))

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["error_category"], "tool_timeout")
        self.assertTrue(response.json()["recoverable"])
        self.assertIn("timeout", response.json()["error_message"])
        self.assertEqual(trace["final_status"], "error")
        self.assertEqual(trace["error_category"], "tool_timeout")
        self.assertEqual(trace["tool_failures"][0]["name"], "agent_error")
        self.assertEqual(trace["tool_failures"][0]["category"], "tool_timeout")

    def test_non_streaming_chat_retries_recoverable_failure_once(self) -> None:
        agent = _FlakyRecoverableAgent()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            traces_dir = tmp_path / "traces"
            data_users_dir = tmp_path / "users"
            with patch.object(ss_mod, "SESSIONS_DIR", tmp_path), patch.object(us_mod, "DATA_USERS_DIR", data_users_dir), patch.object(tr_mod, "TRACES_DIR", traces_dir), patch.object(
                app_mod, "build_agent", return_value=agent
            ):
                client = TestClient(app_mod.app)
                response = client.post(
                    "/api/chat",
                    json={"message": "say hello", "session_id": "main", "stream": False},
                )
                trace_files = list(traces_dir.glob("*.json"))
                trace = json.loads(trace_files[0].read_text(encoding="utf-8"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["reply"], "recovered reply")
        self.assertEqual(agent.calls, 2)
        self.assertEqual(trace["final_status"], "success")
        self.assertEqual(trace["retry_count"], 1)
        self.assertEqual(trace["events"][-2]["kind"], "runtime_retry")

    def test_streaming_chat_emits_friendly_final_on_failure(self) -> None:
        class _FailingStreamAgent:
            async def astream_events(self, payload, version="v2"):
                if False:
                    yield {"type": "thought", "data": {"content": "unused"}}
                raise RuntimeError("knowledge retrieval failed: vector index unavailable")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            traces_dir = tmp_path / "traces"
            data_users_dir = tmp_path / "users"
            with patch.object(ss_mod, "SESSIONS_DIR", tmp_path), patch.object(us_mod, "DATA_USERS_DIR", data_users_dir), patch.object(tr_mod, "TRACES_DIR", traces_dir), patch.object(
                app_mod, "build_agent", return_value=_FailingStreamAgent()
            ):
                client = TestClient(app_mod.app)
                response = client.post(
                    "/api/chat",
                    json={"message": "say hello", "session_id": "main", "stream": True},
                )
                trace_files = list(traces_dir.glob("*.json"))
                trace = json.loads(trace_files[0].read_text(encoding="utf-8"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("event: tool_result", response.text)
        self.assertIn("knowledge_retrieval_failure", response.text)
        self.assertIn("temporarily unavailable", response.text)
        self.assertEqual(trace["final_status"], "error")
        self.assertEqual(trace["error_category"], "knowledge_retrieval_failure")


if __name__ == "__main__":
    unittest.main()
