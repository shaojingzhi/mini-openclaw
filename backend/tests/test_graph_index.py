"""Unit tests for the file-backed graph index."""

from __future__ import annotations

import importlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

graph_mod = importlib.import_module("backend.graph.index")


class GraphIndexTests(unittest.TestCase):
    def test_build_graph_extracts_nodes_and_edges(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            knowledge = root / "knowledge"
            skills = root / "skills"
            workspace = root / "workspace"
            traces = root / "traces"
            for folder in (knowledge, skills, workspace, traces):
                folder.mkdir(parents=True)

            (knowledge / "agent_notes.md").write_text(
                "# Agent Notes\nUse memory with retrieval for interview answers.\n",
                encoding="utf-8",
            )
            skill_dir = skills / "research"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                "---\nname: research\n---\n# Research\nUse fetch_url and python_repl.\n",
                encoding="utf-8",
            )
            (workspace / "AGENTS.md").write_text(
                "# Agent Protocol\nReference memory and traces.\n",
                encoding="utf-8",
            )
            (traces / "trace_1.json").write_text(
                json.dumps(
                    {
                        "trace_id": "trace_1",
                        "session_id": "main",
                        "final_status": "failed",
                        "latency_ms": 12,
                        "tool_calls": [{"name": "fetch_url"}],
                        "tool_failures": [{"name": "terminal"}],
                        "error_category": "tool_timeout",
                    }
                ),
                encoding="utf-8",
            )

            with patch.object(graph_mod, "PROJECT_ROOT", root), patch.object(
                graph_mod, "KNOWLEDGE_DIR", knowledge
            ), patch.object(graph_mod, "SKILLS_DIR", skills), patch.object(
                graph_mod, "WORKSPACE_DIR", workspace
            ), patch.object(
                graph_mod, "TRACES_DIR", traces
            ):
                graph = graph_mod.build_graph()

        node_types = {node["type"] for node in graph["nodes"]}
        edge_types = {edge["type"] for edge in graph["edges"]}
        labels = {node["label"] for node in graph["nodes"]}

        self.assertIn("document", node_types)
        self.assertIn("skill", node_types)
        self.assertIn("workspace_file", node_types)
        self.assertIn("trace", node_types)
        self.assertIn("tool", node_types)
        self.assertIn("concept", node_types)
        self.assertIn("heading", node_types)
        self.assertIn("contains", edge_types)
        self.assertIn("mentions", edge_types)
        self.assertIn("uses_tool", edge_types)
        self.assertIn("failed_at", edge_types)
        self.assertIn("fetch_url", labels)
        self.assertIn("terminal", labels)

    def test_save_graph_is_deterministic_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "graph.json"
            graph = {
                "schema_version": 1,
                "generated_at": "fixed",
                "sources": {},
                "nodes": [
                    {"id": "b", "type": "concept", "label": "b", "metadata": {}},
                    {"id": "a", "type": "concept", "label": "a", "metadata": {}},
                ],
                "edges": [],
            }
            graph_mod.save_graph(graph, out)
            first = out.read_text(encoding="utf-8")
            graph_mod.save_graph(graph, out)
            second = out.read_text(encoding="utf-8")

        self.assertEqual(first, second)
        self.assertTrue(first.endswith("\n"))

    def test_missing_sources_build_empty_graph(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(graph_mod, "PROJECT_ROOT", root), patch.object(
                graph_mod, "KNOWLEDGE_DIR", root / "missing-knowledge"
            ), patch.object(graph_mod, "SKILLS_DIR", root / "missing-skills"), patch.object(
                graph_mod, "WORKSPACE_DIR", root / "missing-workspace"
            ), patch.object(
                graph_mod, "TRACES_DIR", root / "missing-traces"
            ):
                graph = graph_mod.build_graph()

        self.assertEqual(graph["nodes"], [])
        self.assertEqual(graph["edges"], [])

    def test_rebuild_graph_writes_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            knowledge = root / "knowledge"
            knowledge.mkdir()
            (knowledge / "one.md").write_text("# One\nGraph RAG note.\n", encoding="utf-8")
            output = root / "out" / "knowledge_graph.json"
            with patch.object(graph_mod, "PROJECT_ROOT", root), patch.object(
                graph_mod, "KNOWLEDGE_DIR", knowledge
            ), patch.object(graph_mod, "SKILLS_DIR", root / "skills"), patch.object(
                graph_mod, "WORKSPACE_DIR", root / "workspace"
            ), patch.object(
                graph_mod, "TRACES_DIR", root / "traces"
            ):
                graph = graph_mod.rebuild_graph(output)
                self.assertTrue(output.exists())
                loaded = json.loads(output.read_text(encoding="utf-8"))
                self.assertEqual(len(loaded["nodes"]), len(graph["nodes"]))
                self.assertGreaterEqual(len(loaded["nodes"]), 1)


if __name__ == "__main__":
    unittest.main()
