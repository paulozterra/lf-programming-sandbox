from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable

from .hashutil import sha256_json

NODE_KINDS = {
    "REQUIREMENT", "RULE", "DECISION", "RETRIEVAL", "FILE", "SYMBOL", "TEST", "ORACLE", "RESULT", "EVIDENCE"
}
RELATIONS = {
    "retrieved_for", "constrains", "implements", "contains", "verified_by", "produces", "evidenced_by", "derived_from"
}


class TraceabilityError(ValueError):
    """Raised when a traceability graph cannot prove its own links."""


@dataclass(frozen=True)
class TraceNode:
    node_id: str
    kind: str
    label: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TraceEdge:
    source: str
    target: str
    relation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TraceabilityGraph:
    nodes: tuple[TraceNode, ...]
    edges: tuple[TraceEdge, ...]
    graph_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "graph_sha256": self.graph_sha256,
        }


def _node(value: Any) -> TraceNode:
    if not isinstance(value, dict):
        raise TraceabilityError("node must be an object")
    node_id = value.get("node_id")
    kind = value.get("kind")
    label = value.get("label")
    metadata = value.get("metadata", {})
    if not isinstance(node_id, str) or not node_id or len(node_id) > 512:
        raise TraceabilityError("node_id invalid")
    if kind not in NODE_KINDS:
        raise TraceabilityError(f"node kind invalid: {kind}")
    if not isinstance(label, str) or not label or len(label.encode("utf-8")) > 20_000:
        raise TraceabilityError("node label invalid")
    if not isinstance(metadata, dict):
        raise TraceabilityError("node metadata must be an object")
    return TraceNode(node_id, kind, label, dict(metadata))


def _edge(value: Any) -> TraceEdge:
    if not isinstance(value, dict):
        raise TraceabilityError("edge must be an object")
    source, target, relation = value.get("source"), value.get("target"), value.get("relation")
    if not isinstance(source, str) or not source or not isinstance(target, str) or not target:
        raise TraceabilityError("edge endpoints invalid")
    if relation not in RELATIONS:
        raise TraceabilityError(f"edge relation invalid: {relation}")
    return TraceEdge(source, target, relation)


def _payload_digest(nodes: tuple[TraceNode, ...], edges: tuple[TraceEdge, ...]) -> str:
    return sha256_json({"schema_version": 1, "nodes": [n.to_dict() for n in nodes], "edges": [e.to_dict() for e in edges]})


def make_traceability_graph(nodes: Iterable[TraceNode], edges: Iterable[TraceEdge]) -> TraceabilityGraph:
    sorted_nodes = tuple(sorted(nodes, key=lambda item: item.node_id))
    sorted_edges = tuple(sorted(edges, key=lambda item: (item.source, item.target, item.relation)))
    graph = TraceabilityGraph(sorted_nodes, sorted_edges, _payload_digest(sorted_nodes, sorted_edges))
    problems = validate_traceability_graph(graph)
    if problems:
        raise TraceabilityError(f"traceability graph invalid: {problems}")
    return graph


def traceability_graph_from_dict(value: Any) -> TraceabilityGraph:
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise TraceabilityError("traceability graph schema_version must be 1")
    if not isinstance(value.get("nodes"), list) or not isinstance(value.get("edges"), list):
        raise TraceabilityError("traceability graph requires nodes[] and edges[]")
    nodes = tuple(sorted((_node(item) for item in value["nodes"]), key=lambda item: item.node_id))
    edges = tuple(sorted((_edge(item) for item in value["edges"]), key=lambda item: (item.source, item.target, item.relation)))
    digest = value.get("graph_sha256")
    if not isinstance(digest, str) or digest != _payload_digest(nodes, edges):
        raise TraceabilityError("graph_sha256 mismatch")
    graph = TraceabilityGraph(nodes, edges, digest)
    problems = validate_traceability_graph(graph)
    if problems:
        raise TraceabilityError(f"traceability graph invalid: {problems}")
    return graph


def _ancestors(node_id: str, edges: tuple[TraceEdge, ...]) -> set[str]:
    reverse: dict[str, set[str]] = {}
    for edge in edges:
        reverse.setdefault(edge.target, set()).add(edge.source)
    visited: set[str] = set()
    pending = list(reverse.get(node_id, set()))
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        pending.extend(sorted(reverse.get(current, set()) - visited))
    return visited


def important_pass_problems(graph: TraceabilityGraph) -> list[str]:
    by_id = {node.node_id: node for node in graph.nodes}
    outgoing: dict[str, list[TraceEdge]] = {}
    for edge in graph.edges:
        outgoing.setdefault(edge.source, []).append(edge)
    problems: list[str] = []
    for node in graph.nodes:
        if node.kind != "RESULT" or node.metadata.get("status") != "PASS" or node.metadata.get("important") is not True:
            continue
        evidence_targets = [edge.target for edge in outgoing.get(node.node_id, []) if edge.relation == "evidenced_by"]
        if not evidence_targets or not any(by_id.get(target) and by_id[target].kind == "EVIDENCE" for target in evidence_targets):
            problems.append(f"{node.node_id}:PASS_WITHOUT_EVIDENCE")
        ancestors = {by_id[item].kind for item in _ancestors(node.node_id, graph.edges) if item in by_id}
        if not ancestors.intersection({"REQUIREMENT", "RULE", "DECISION"}):
            problems.append(f"{node.node_id}:PASS_WITHOUT_REQUIREMENT_OR_GOVERNANCE")
        if not ancestors.intersection({"FILE", "SYMBOL"}):
            problems.append(f"{node.node_id}:PASS_WITHOUT_IMPLEMENTATION")
        if not ancestors.intersection({"TEST", "ORACLE"}):
            problems.append(f"{node.node_id}:PASS_WITHOUT_VERIFIER")
    return sorted(problems)


def validate_traceability_graph(graph: TraceabilityGraph) -> list[str]:
    problems: list[str] = []
    ids = [node.node_id for node in graph.nodes]
    if len(ids) != len(set(ids)):
        problems.append("DUPLICATE_NODE_ID")
    known = set(ids)
    edge_keys = [(edge.source, edge.target, edge.relation) for edge in graph.edges]
    if len(edge_keys) != len(set(edge_keys)):
        problems.append("DUPLICATE_EDGE")
    for edge in graph.edges:
        if edge.source not in known or edge.target not in known:
            problems.append(f"DANGLING_EDGE:{edge.source}->{edge.target}")
        if edge.source == edge.target:
            problems.append(f"SELF_EDGE:{edge.source}")
    if graph.graph_sha256 != _payload_digest(graph.nodes, graph.edges):
        problems.append("GRAPH_SHA256_MISMATCH")
    problems.extend(important_pass_problems(graph))
    return sorted(set(problems))


def traceability_quality_passes(graph: TraceabilityGraph) -> bool:
    return not validate_traceability_graph(graph)


def build_verification_trace(verification: dict[str, Any], retrieval: dict[str, Any] | None = None) -> TraceabilityGraph:
    nodes: dict[str, TraceNode] = {}
    edges: set[tuple[str, str, str]] = set()

    def add_node(node_id: str, kind: str, label: str, metadata: dict[str, Any] | None = None) -> None:
        nodes.setdefault(node_id, TraceNode(node_id, kind, label, metadata or {}))

    def add_edge(source: str, target: str, relation: str) -> None:
        edges.add((source, target, relation))

    retrieval_nodes: list[str] = []
    if isinstance(retrieval, dict):
        for item in retrieval.get("selected", []):
            if not isinstance(item, dict):
                continue
            source = item.get("source")
            kind = "RULE" if source in {"rules", "preventions", "best_practices", "ekb"} else "DECISION" if source == "decisions" else "RETRIEVAL"
            record_id = str(item.get("record_id"))
            node_id = f"knowledge:{source}:{record_id}"
            add_node(node_id, kind, str(item.get("title") or record_id), {"score": item.get("score"), "provenance": item.get("provenance")})
            retrieval_nodes.append(node_id)

    for key, value in sorted(verification.items()):
        if not isinstance(value, dict):
            continue
        requirement_id = f"requirement:{key}"
        add_node(requirement_id, "REQUIREMENT", str(value.get("requirement") or key), {"code": key})
        for knowledge_id in retrieval_nodes:
            add_edge(knowledge_id, requirement_id, "retrieved_for")
        implementation_nodes: list[str] = []
        for path in value.get("code", []):
            file_id = f"file:{path}"
            add_node(file_id, "FILE", str(path), {})
            add_edge(requirement_id, file_id, "implements")
            implementation_nodes.append(file_id)
        verifier_nodes: list[str] = []
        for test in value.get("test_or_oracle", []):
            kind = "ORACLE" if "oracle" in str(test).lower() else "TEST"
            test_id = f"verifier:{test}"
            add_node(test_id, kind, str(test), {})
            for file_id in implementation_nodes:
                add_edge(file_id, test_id, "verified_by")
            verifier_nodes.append(test_id)
        result_id = f"result:{key}"
        status = value.get("result")
        add_node(result_id, "RESULT", f"{key}={status}", {"status": status, "important": True})
        for verifier_id in verifier_nodes:
            add_edge(verifier_id, result_id, "produces")
        evidence = value.get("evidence")
        evidence_id = f"evidence:{key}"
        add_node(evidence_id, "EVIDENCE", f"Evidence for {key}", {"payload": evidence})
        add_edge(result_id, evidence_id, "evidenced_by")

    return make_traceability_graph(nodes.values(), (TraceEdge(*item) for item in edges))
