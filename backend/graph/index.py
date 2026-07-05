"""File-backed graph index for agent knowledge.

This module builds a lightweight, deterministic graph from Mini-OpenClaw's
local knowledge, skills, workspace files, and trace logs. It intentionally uses
plain JSON storage so graph-assisted retrieval can stay inspectable and cheap.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
KNOWLEDGE_DIR: Path = PROJECT_ROOT / "backend" / "knowledge"
SKILLS_DIR: Path = PROJECT_ROOT / "backend" / "skills"
WORKSPACE_DIR: Path = PROJECT_ROOT / "backend" / "workspace"
TRACES_DIR: Path = PROJECT_ROOT / "backend" / "data" / "traces"
GRAPH_DIR: Path = PROJECT_ROOT / "backend" / "data" / "graph"
GRAPH_PATH: Path = GRAPH_DIR / "knowledge_graph.json"

TEXT_SUFFIXES: set[str] = {".md", ".txt"}
TOOL_NAMES: set[str] = {
    "fetch_url",
    "python_repl",
    "read_file",
    "search_knowledge_base",
    "terminal",
}
KEYWORD_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
MARKDOWN_LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def _stable_id(kind: str, value: str) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]
    return f"{kind}:{digest}"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _iter_files(root: Path, *, suffixes: set[str] | None = None) -> list[Path]:
    if not root.exists() or not root.is_dir():
        return []

    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.name.startswith("."):
            continue
        if suffixes is not None and path.suffix.lower() not in suffixes:
            continue
        files.append(path)
    return sorted(files, key=lambda p: str(p.relative_to(root)))


def _relative_path(path: Path) -> str:
    try:
        return path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _node(
    node_id: str,
    node_type: str,
    label: str,
    *,
    path: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": node_id,
        "type": node_type,
        "label": label,
        "metadata": metadata or {},
    }
    if path is not None:
        payload["path"] = path
    return payload


def _edge(
    source: str,
    target: str,
    edge_type: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": _stable_id("edge", f"{source}|{edge_type}|{target}"),
        "source": source,
        "target": target,
        "type": edge_type,
        "metadata": metadata or {},
    }


def _add_node(nodes: dict[str, dict[str, Any]], node: dict[str, Any]) -> None:
    nodes.setdefault(str(node["id"]), node)


def _add_edge(edges: dict[str, dict[str, Any]], edge: dict[str, Any]) -> None:
    edges.setdefault(str(edge["id"]), edge)


def _concepts_from_text(text: str, *, limit: int = 12) -> list[str]:
    counts: dict[str, int] = {}
    for match in KEYWORD_PATTERN.finditer(text):
        token = match.group(0)
        lowered = token.lower()
        if lowered in {"the", "and", "for", "with", "from", "that", "this"}:
            continue
        counts[lowered] = counts.get(lowered, 0) + 1
    return [
        word
        for word, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[
            :limit
        ]
    ]


def _add_markdown_file(
    nodes: dict[str, dict[str, Any]],
    edges: dict[str, dict[str, Any]],
    path: Path,
    *,
    root: Path,
    node_type: str,
) -> None:
    rel_path = _relative_path(path)
    text = _read_text(path)
    node_id = _stable_id(node_type, rel_path)
    label = path.parent.name if node_type == "skill" else path.name
    _add_node(
        nodes,
        _node(
            node_id,
            node_type,
            label,
            path=rel_path,
            metadata={"chars": len(text), "source_root": _relative_path(root)},
        ),
    )

    for level, title in HEADING_PATTERN.findall(text):
        heading_label = title.strip()
        heading_id = _stable_id("heading", f"{rel_path}#{heading_label}")
        _add_node(
            nodes,
            _node(
                heading_id,
                "heading",
                heading_label,
                path=rel_path,
                metadata={"level": len(level)},
            ),
        )
        _add_edge(edges, _edge(node_id, heading_id, "contains"))

    for concept in _concepts_from_text(text):
        concept_id = _stable_id("concept", concept)
        _add_node(nodes, _node(concept_id, "concept", concept))
        _add_edge(edges, _edge(node_id, concept_id, "mentions"))

    for link_target in sorted(set(MARKDOWN_LINK_PATTERN.findall(text))):
        if not link_target or "://" in link_target:
            continue
        target_path = (path.parent / link_target).resolve()
        if target_path.exists():
            target_rel = _relative_path(target_path)
            target_id = _stable_id("document", target_rel)
            _add_node(
                nodes,
                _node(target_id, "document", target_path.name, path=target_rel),
            )
            _add_edge(edges, _edge(node_id, target_id, "references"))

    if node_type == "skill":
        lowered_text = text.lower()
        for tool_name in sorted(TOOL_NAMES):
            if tool_name in lowered_text:
                tool_id = _stable_id("tool", tool_name)
                _add_node(nodes, _node(tool_id, "tool", tool_name))
                _add_edge(edges, _edge(node_id, tool_id, "uses_tool"))


def _add_trace_file(
    nodes: dict[str, dict[str, Any]],
    edges: dict[str, dict[str, Any]],
    path: Path,
) -> None:
    try:
        trace = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return

    trace_id = str(trace.get("trace_id") or path.stem)
    node_id = _stable_id("trace", trace_id)
    _add_node(
        nodes,
        _node(
            node_id,
            "trace",
            trace_id,
            path=_relative_path(path),
            metadata={
                "final_status": trace.get("final_status"),
                "session_id": trace.get("session_id"),
                "latency_ms": trace.get("latency_ms"),
            },
        ),
    )

    for tool_call in trace.get("tool_calls", []) or []:
        tool_name = str(tool_call.get("name") or "")
        if not tool_name:
            continue
        tool_id = _stable_id("tool", tool_name)
        _add_node(nodes, _node(tool_id, "tool", tool_name))
        _add_edge(edges, _edge(node_id, tool_id, "uses_tool"))

    for failure in trace.get("tool_failures", []) or []:
        tool_name = str(failure.get("name") or failure.get("tool") or "")
        if not tool_name:
            continue
        tool_id = _stable_id("tool", tool_name)
        _add_node(nodes, _node(tool_id, "tool", tool_name))
        _add_edge(edges, _edge(node_id, tool_id, "failed_at"))

    error_category = trace.get("error_category")
    if error_category:
        concept_id = _stable_id("concept", str(error_category))
        _add_node(nodes, _node(concept_id, "concept", str(error_category)))
        _add_edge(edges, _edge(node_id, concept_id, "mentions"))


def build_graph() -> dict[str, Any]:
    """Build a deterministic graph payload from local agent artifacts."""
    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[str, dict[str, Any]] = {}

    for path in _iter_files(KNOWLEDGE_DIR, suffixes=TEXT_SUFFIXES):
        _add_markdown_file(
            nodes, edges, path, root=KNOWLEDGE_DIR, node_type="document"
        )
    for path in _iter_files(SKILLS_DIR, suffixes={".md"}):
        if path.name == "SKILL.md":
            _add_markdown_file(nodes, edges, path, root=SKILLS_DIR, node_type="skill")
    for path in _iter_files(WORKSPACE_DIR, suffixes=TEXT_SUFFIXES):
        _add_markdown_file(
            nodes, edges, path, root=WORKSPACE_DIR, node_type="workspace_file"
        )
    for path in _iter_files(TRACES_DIR, suffixes={".json"}):
        _add_trace_file(nodes, edges, path)

    return {
        "schema_version": 1,
        "generated_at": _utc_now_iso(),
        "sources": {
            "knowledge": _relative_path(KNOWLEDGE_DIR),
            "skills": _relative_path(SKILLS_DIR),
            "workspace": _relative_path(WORKSPACE_DIR),
            "traces": _relative_path(TRACES_DIR),
        },
        "nodes": sorted(nodes.values(), key=lambda item: str(item["id"])),
        "edges": sorted(edges.values(), key=lambda item: str(item["id"])),
    }


def save_graph(graph: dict[str, Any], path: Path = GRAPH_PATH) -> Path:
    """Persist a graph payload as deterministic JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(graph, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def rebuild_graph(path: Path = GRAPH_PATH) -> dict[str, Any]:
    """Build and persist the local knowledge graph."""
    graph = build_graph()
    save_graph(graph, path)
    return graph


def load_graph(path: Path = GRAPH_PATH) -> dict[str, Any] | None:
    """Load a persisted graph payload if it exists and is valid JSON."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def graph_summary(graph: dict[str, Any]) -> dict[str, Any]:
    """Return compact counts for graph diagnostics."""
    node_counts: dict[str, int] = {}
    edge_counts: dict[str, int] = {}
    for node in graph.get("nodes", []):
        node_type = str(node.get("type", "unknown"))
        node_counts[node_type] = node_counts.get(node_type, 0) + 1
    for edge in graph.get("edges", []):
        edge_type = str(edge.get("type", "unknown"))
        edge_counts[edge_type] = edge_counts.get(edge_type, 0) + 1
    return {
        "schema_version": graph.get("schema_version"),
        "node_count": len(graph.get("nodes", [])),
        "edge_count": len(graph.get("edges", [])),
        "node_counts": dict(sorted(node_counts.items())),
        "edge_counts": dict(sorted(edge_counts.items())),
        "sources": graph.get("sources", {}),
    }


def expand_graph_evidence(
    query: str,
    *,
    graph: dict[str, Any] | None = None,
    max_hops: int = 2,
    max_nodes: int = 8,
) -> dict[str, Any]:
    """Find direct graph matches and nearby evidence nodes for a query."""
    graph = graph if graph is not None else load_graph()
    if not graph:
        return {
            "available": False,
            "direct_node_ids": [],
            "expanded_node_ids": [],
            "edge_types": [],
            "evidence": [],
        }

    query_terms = set(_concepts_from_text(query, limit=12))
    if not query_terms:
        query_terms = {term.lower() for term in query.split() if term.strip()}

    nodes_by_id = {str(node["id"]): node for node in graph.get("nodes", [])}
    adjacency: dict[str, list[dict[str, Any]]] = {}
    for edge in graph.get("edges", []):
        source = str(edge.get("source"))
        target = str(edge.get("target"))
        adjacency.setdefault(source, []).append(edge)
        adjacency.setdefault(target, []).append(
            {
                **edge,
                "source": target,
                "target": source,
                "metadata": {**edge.get("metadata", {}), "reverse": True},
            }
        )

    direct_ids: list[str] = []
    for node in graph.get("nodes", []):
        haystack = " ".join(
            [
                str(node.get("label", "")),
                str(node.get("path", "")),
                json.dumps(node.get("metadata", {}), ensure_ascii=False),
            ]
        ).lower()
        if any(term in haystack for term in query_terms):
            direct_ids.append(str(node["id"]))

    visited = set(direct_ids)
    frontier = list(direct_ids)
    expanded_ids: list[str] = []
    edge_types: set[str] = set()

    for _ in range(max_hops):
        next_frontier: list[str] = []
        for node_id in frontier:
            for edge in sorted(adjacency.get(node_id, []), key=lambda item: str(item["id"])):
                edge_types.add(str(edge.get("type")))
                target_id = str(edge.get("target"))
                if target_id in visited:
                    continue
                visited.add(target_id)
                expanded_ids.append(target_id)
                next_frontier.append(target_id)
                if len(expanded_ids) >= max_nodes:
                    break
            if len(expanded_ids) >= max_nodes:
                break
        if len(expanded_ids) >= max_nodes or not next_frontier:
            break
        frontier = next_frontier

    evidence_ids = direct_ids + expanded_ids
    evidence = [
        nodes_by_id[node_id]
        for node_id in evidence_ids[:max_nodes]
        if node_id in nodes_by_id
    ]
    return {
        "available": True,
        "direct_node_ids": direct_ids,
        "expanded_node_ids": expanded_ids[:max_nodes],
        "edge_types": sorted(edge_types),
        "evidence": evidence,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rebuild Mini-OpenClaw graph index")
    parser.add_argument(
        "--output",
        default=str(GRAPH_PATH),
        help="Path for the generated knowledge graph JSON",
    )
    args = parser.parse_args(argv)
    graph = rebuild_graph(Path(args.output))
    print(
        f"Wrote {len(graph['nodes'])} nodes and {len(graph['edges'])} edges to {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "GRAPH_PATH",
    "build_graph",
    "expand_graph_evidence",
    "graph_summary",
    "load_graph",
    "main",
    "rebuild_graph",
    "save_graph",
]
