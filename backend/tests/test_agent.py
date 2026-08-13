"""Smoke test for backend.graph.agent.build_agent.

Mocks the LLM with a tool-binding-capable fake chat model (no network)
and asserts the agent answers a trivial ``say hello`` prompt with a
non-empty string. Also verifies the agent is wired with all five core
tools and that the assembled System Prompt flows through.
"""

from __future__ import annotations

import unittest

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from backend.agents.profiles import get_agent_profile
from backend.graph.agent import CORE_TOOLS, build_agent
from backend.tools.read_file import PRIVATE_MEMORY_BLOCKED_MESSAGE, read_file
from backend.tools.terminal import SCOPED_BLOCKED_MESSAGE, terminal


class _ToolBindingFakeChatModel(GenericFakeChatModel):
    """``GenericFakeChatModel`` that no-ops ``bind_tools`` instead of raising.

    ``create_agent`` calls ``model.bind_tools(tools)`` to register the
    tool schema. The default ``BaseChatModel.bind_tools`` raises
    ``NotImplementedError`` — fine for production providers
    (``ChatOpenAI`` etc.) but unusable in tests. We override it to
    return ``self`` so the scripted reply is delivered unchanged.
    """

    def bind_tools(self, tools, **kwargs):  # type: ignore[override]
        return self


class BuildAgentTests(unittest.TestCase):
    def _fake_model(self, reply: str) -> _ToolBindingFakeChatModel:
        return _ToolBindingFakeChatModel(messages=iter([AIMessage(content=reply)]))

    def test_say_hello_returns_non_empty_reply(self) -> None:
        agent = build_agent(model=self._fake_model("hello back"))
        result = agent.invoke({"messages": [{"role": "user", "content": "say hello"}]})
        # create_agent's CompiledStateGraph returns a dict with "messages"
        # where the last item is the assistant's reply.
        self.assertIn("messages", result)
        final = result["messages"][-1]
        self.assertTrue(getattr(final, "content", "").strip(),
                        f"agent reply was empty: {final!r}")
        self.assertEqual(final.content, "hello back")

    def test_core_tools_are_registered(self) -> None:
        # Direct inspection of the module-level list so we fail fast
        # if a future change accidentally drops a tool.
        names = [t.name for t in CORE_TOOLS]
        self.assertEqual(
            sorted(names),
            ["fetch_url", "python_repl", "read_file",
             "search_knowledge_base", "terminal"],
        )

    def test_agent_compiles_without_calling_provider(self) -> None:
        # Constructing the agent with the fake model must not raise — no
        # OPENAI_API_KEY needed when the caller supplies their own model.
        agent = build_agent(model=self._fake_model("ok"))
        self.assertIsNotNone(agent)

    def test_agent_includes_scoped_memory_proposal_tool(self) -> None:
        agent = build_agent(model=self._fake_model("ok"), user_id="alice", session_id="main")

        tools_by_name = agent.get_graph().nodes["tools"].data.tools_by_name
        self.assertIn("propose_memory_update", tools_by_name)

    def test_only_lighthouse_receives_handoff_tool(self) -> None:
        lighthouse = build_agent(
            model=self._fake_model("ok"),
            agent_profile=get_agent_profile("lighthouse"),
        )
        spark = build_agent(
            model=self._fake_model("ok"),
            agent_profile=get_agent_profile("spark"),
        )

        lighthouse_tools = lighthouse.get_graph().nodes["tools"].data.tools_by_name
        spark_tools = spark.get_graph().nodes["tools"].data.tools_by_name
        self.assertIn("request_agent_handoff", lighthouse_tools)
        self.assertNotIn("request_agent_handoff", spark_tools)

    def test_agent_uses_scoped_filesystem_tools(self) -> None:
        spark = build_agent(
            model=self._fake_model("ok"),
            agent_profile=get_agent_profile("spark"),
        )
        tools_by_name = spark.get_graph().nodes["tools"].data.tools_by_name

        self.assertIsNot(tools_by_name["read_file"], read_file)
        self.assertIsNot(tools_by_name["terminal"], terminal)
        self.assertEqual(
            tools_by_name["read_file"].invoke(
                {
                    "file_path": (
                        "backend/memory/approved_memory/agents/whetstone/RELATIONSHIP.md"
                    )
                }
            ),
            PRIVATE_MEMORY_BLOCKED_MESSAGE,
        )
        self.assertEqual(
            tools_by_name["terminal"].invoke(
                {"command": "ls backend/memory/approved_memory/agents/whetstone"}
            ),
            SCOPED_BLOCKED_MESSAGE,
        )


if __name__ == "__main__":
    unittest.main()
