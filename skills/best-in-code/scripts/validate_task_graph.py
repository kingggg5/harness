#!/usr/bin/env python3
"""Fail-closed validator for optional Harness task graphs."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict, deque
from pathlib import Path, PurePosixPath
from typing import Any

sys.dont_write_bytecode = True


MAX_BYTES = 256 * 1024
MAX_NODES = 64
MAX_EDGES = 128
ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
PROJECT_ID_PATTERN = re.compile(r"^project-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")
ROOT_FIELDS = {
	"schema_version", "graph_id", "project_id", "run_id", "coordinator",
	"isolation_strategy", "base_revision", "max_parallel", "max_transitions",
	"entry_nodes", "nodes", "edges",
}
NODE_FIELDS = {
	"id", "kind", "owner", "objective", "inputs", "optional_inputs", "outputs",
	"read_scope", "write_scope", "max_attempts", "timeout_seconds", "side_effect",
	"success_criteria", "join", "idempotency_key",
}
EDGE_FIELDS = {"from", "to", "type", "condition", "consumes", "max_rounds"}
NODE_KINDS = {"deterministic", "model", "human", "merge"}
SIDE_EFFECTS = {"none", "reversible", "consequential"}
ISOLATION_STRATEGIES = {"same-worktree-sequential", "provider-isolated", "git-worktree"}
EDGE_TYPES = {"data", "control", "loop"}
EDGE_CONDITIONS = {"always", "on_success", "on_failure", "on_approve", "on_reject"}


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Validate a Harness TASK-GRAPH.json contract")
	parser.add_argument("--graph", required=True, help="Path to TASK-GRAPH.json")
	parser.add_argument("--json", action="store_true", help="Print structured output")
	return parser.parse_args()


def is_int(value: Any, low: int, high: int) -> bool:
	return isinstance(value, int) and not isinstance(value, bool) and low <= value <= high


def check_string_list(value: Any, field: str, errors: list[str], *, allow_empty: bool = True) -> list[str]:
	if not isinstance(value, list) or (not allow_empty and not value):
		errors.append(f"{field} must be {'a non-empty' if not allow_empty else 'an'} array of unique strings")
		return []
	if any(not isinstance(item, str) or not item.strip() or len(item.encode("utf-8")) > 256 for item in value):
		errors.append(f"{field} entries must be non-empty strings of at most 256 UTF-8 bytes")
		return []
	if len(value) != len(set(value)):
		errors.append(f"{field} entries must be unique")
	return value


def valid_scope(value: str) -> bool:
	if "\\" in value or "*" in value or "?" in value or "[" in value:
		return False
	path = PurePosixPath(value)
	return not path.is_absolute() and value not in {"", "/"} and ".." not in path.parts


def scope_overlaps(left: str, right: str) -> bool:
	if left == "." or right == ".":
		return True
	left_parts = PurePosixPath(left).parts
	right_parts = PurePosixPath(right).parts
	shorter = min(len(left_parts), len(right_parts))
	return left_parts[:shorter] == right_parts[:shorter]


def reachable(start: str, target: str, adjacency: dict[str, set[str]]) -> bool:
	queue = deque([start])
	seen = {start}
	while queue:
		current = queue.popleft()
		for nxt in adjacency[current]:
			if nxt == target:
				return True
			if nxt not in seen:
				seen.add(nxt)
				queue.append(nxt)
	return False


def validate_graph(data: Any) -> list[str]:
	errors: list[str] = []
	if not isinstance(data, dict):
		return ["graph root must be an object"]
	unknown = set(data) - ROOT_FIELDS
	missing = ROOT_FIELDS - set(data)
	if unknown:
		errors.append(f"graph has unknown fields: {sorted(unknown)}")
	if missing:
		errors.append(f"graph is missing fields: {sorted(missing)}")
	if errors:
		return errors

	if data["schema_version"] != 1:
		errors.append("schema_version must be 1")
	if not isinstance(data["graph_id"], str) or not ID_PATTERN.fullmatch(data["graph_id"]):
		errors.append("graph_id must match ^[a-z][a-z0-9-]{0,63}$")
	if not isinstance(data["project_id"], str) or (data["project_id"] and not PROJECT_ID_PATTERN.fullmatch(data["project_id"])):
		errors.append("project_id must be empty in the starter template or match the canonical Harness Project ID")
	if not isinstance(data["run_id"], str) or (data["run_id"] and not RUN_ID_PATTERN.fullmatch(data["run_id"])):
		errors.append("run_id must be empty in the starter template or a safe 1 to 200 character ID")
	if isinstance(data["project_id"], str) and isinstance(data["run_id"], str) and bool(data["project_id"]) != bool(data["run_id"]):
		errors.append("project_id and run_id must either both be empty in the starter template or both bind an active graph")
	if not isinstance(data["coordinator"], str) or not data["coordinator"].strip():
		errors.append("coordinator must be a non-empty string")
	isolation_strategy = data["isolation_strategy"]
	if not isinstance(isolation_strategy, str) or isolation_strategy not in ISOLATION_STRATEGIES:
		errors.append(f"isolation_strategy must be one of {sorted(ISOLATION_STRATEGIES)}")
	base_revision = data["base_revision"]
	if not isinstance(base_revision, str):
		errors.append("base_revision must be empty in the starter template or an exact 40/64-character lowercase commit ID")
	elif base_revision and not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", base_revision):
		errors.append("base_revision must be empty in the starter template or an exact 40/64-character lowercase commit ID")
	if isinstance(data["run_id"], str) and data["run_id"] and not base_revision:
		errors.append("an active graph requires an exact base_revision")
	if not is_int(data["max_parallel"], 1, 8):
		errors.append("max_parallel must be an integer from 1 to 8")
	elif data["max_parallel"] > 1 and isolation_strategy == "same-worktree-sequential":
		errors.append("max_parallel greater than 1 requires provider-isolated or git-worktree execution")
	if isinstance(isolation_strategy, str) and isolation_strategy in {"provider-isolated", "git-worktree"} and not base_revision:
		errors.append("isolated execution requires an exact base_revision")
	if not is_int(data["max_transitions"], 1, 256):
		errors.append("max_transitions must be an integer from 1 to 256")

	nodes = data["nodes"]
	edges = data["edges"]
	if not isinstance(nodes, list) or not 1 <= len(nodes) <= MAX_NODES:
		errors.append(f"nodes must contain 1 to {MAX_NODES} entries")
		return errors
	if not isinstance(edges, list) or len(edges) > MAX_EDGES:
		errors.append(f"edges must contain at most {MAX_EDGES} entries")
		return errors

	node_by_id: dict[str, dict[str, Any]] = {}
	for index, node in enumerate(nodes):
		label = f"nodes[{index}]"
		if not isinstance(node, dict):
			errors.append(f"{label} must be an object")
			continue
		unknown = set(node) - NODE_FIELDS
		missing = (NODE_FIELDS - {"join", "idempotency_key"}) - set(node)
		if unknown:
			errors.append(f"{label} has unknown fields: {sorted(unknown)}")
		if missing:
			errors.append(f"{label} is missing fields: {sorted(missing)}")
		if missing:
			continue
		node_id = node["id"]
		if not isinstance(node_id, str) or not ID_PATTERN.fullmatch(node_id):
			errors.append(f"{label}.id is invalid")
			continue
		if node_id in node_by_id:
			errors.append(f"duplicate node id: {node_id}")
			continue
		node_by_id[node_id] = node
		if node["kind"] not in NODE_KINDS:
			errors.append(f"{label}.kind must be one of {sorted(NODE_KINDS)}")
		if not isinstance(node["owner"], str) or not node["owner"].strip():
			errors.append(f"{label}.owner must be a non-empty string")
		if not isinstance(node["objective"], str) or not node["objective"].strip() or len(node["objective"].encode("utf-8")) > 1024:
			errors.append(f"{label}.objective must be 1 to 1024 UTF-8 bytes")
		for field in ("inputs", "optional_inputs", "outputs", "read_scope", "write_scope", "success_criteria"):
			check_string_list(node[field], f"{label}.{field}", errors, allow_empty=field not in {"outputs", "success_criteria"})
		for field in ("read_scope", "write_scope"):
			for scope in node[field] if isinstance(node[field], list) else []:
				if isinstance(scope, str) and not valid_scope(scope):
					errors.append(f"{label}.{field} contains unsafe or ambiguous scope: {scope!r}")
		if not is_int(node["max_attempts"], 1, 3):
			errors.append(f"{label}.max_attempts must be an integer from 1 to 3")
		if not is_int(node["timeout_seconds"], 1, 3600):
			errors.append(f"{label}.timeout_seconds must be an integer from 1 to 3600")
		if node["side_effect"] not in SIDE_EFFECTS:
			errors.append(f"{label}.side_effect must be one of {sorted(SIDE_EFFECTS)}")
		if "idempotency_key" in node and (not isinstance(node["idempotency_key"], str) or not node["idempotency_key"].strip() or len(node["idempotency_key"].encode("utf-8")) > 256):
			errors.append(f"{label}.idempotency_key must be 1 to 256 UTF-8 bytes when present")
		if "join" in node and node["join"] not in {"all", "any"}:
			errors.append(f"{label}.join must be all or any")

	entry_nodes = check_string_list(data["entry_nodes"], "entry_nodes", errors, allow_empty=False)
	producers: dict[str, str] = {}
	for node_id, node in node_by_id.items():
		for artifact in node["outputs"]:
			if artifact in producers:
				errors.append(f"artifact {artifact!r} is produced by both {producers[artifact]} and {node_id}")
			else:
				producers[artifact] = node_id
	for node_id in entry_nodes:
		if node_id not in node_by_id:
			errors.append(f"entry node does not exist: {node_id}")

	adjacency: dict[str, set[str]] = defaultdict(set)
	reverse: dict[str, set[str]] = defaultdict(set)
	delivered_initial: dict[str, set[str]] = defaultdict(set)
	loop_edges: list[dict[str, Any]] = []
	seen_edges: set[tuple[str, str, str, str]] = set()
	for index, edge in enumerate(edges):
		label = f"edges[{index}]"
		if not isinstance(edge, dict):
			errors.append(f"{label} must be an object")
			continue
		unknown = set(edge) - EDGE_FIELDS
		missing = (EDGE_FIELDS - {"max_rounds"}) - set(edge)
		if unknown:
			errors.append(f"{label} has unknown fields: {sorted(unknown)}")
		if missing:
			errors.append(f"{label} is missing fields: {sorted(missing)}")
		if missing:
			continue
		source = edge["from"]
		target = edge["to"]
		if source not in node_by_id or target not in node_by_id:
			errors.append(f"{label} references an unknown node")
			continue
		if source == target:
			errors.append(f"{label} self-edges are not allowed")
		edge_type = edge["type"]
		condition = edge["condition"]
		if edge_type not in EDGE_TYPES:
			errors.append(f"{label}.type must be one of {sorted(EDGE_TYPES)}")
			continue
		if condition not in EDGE_CONDITIONS:
			errors.append(f"{label}.condition must be one of {sorted(EDGE_CONDITIONS)}")
		elif condition in {"on_approve", "on_reject"} and node_by_id[source]["kind"] != "human":
			errors.append(f"{label}.{condition} must originate from a human node")
		consumes = check_string_list(edge["consumes"], f"{label}.consumes", errors, allow_empty=edge_type == "control")
		if edge_type in {"data", "loop"} and not consumes:
			errors.append(f"{label} {edge_type} edge must consume at least one artifact; remove fake edges")
		if edge_type == "control" and consumes:
			errors.append(f"{label} control edge cannot consume artifacts; use a data edge")
		for artifact in consumes:
			if artifact not in node_by_id[source].get("outputs", []):
				errors.append(f"{label} consumes {artifact!r}, which is not produced by {source}")
			accepted = node_by_id[target].get("inputs", []) + node_by_id[target].get("optional_inputs", [])
			if artifact not in accepted:
				errors.append(f"{label} delivers {artifact!r}, which {target} does not declare as input")
		key = (source, target, edge_type, condition)
		if key in seen_edges:
			errors.append(f"duplicate edge: {key}")
		seen_edges.add(key)
		if edge_type == "loop":
			if not is_int(edge.get("max_rounds"), 1, 5):
				errors.append(f"{label}.max_rounds must be an integer from 1 to 5")
			loop_edges.append(edge)
		elif "max_rounds" in edge:
			errors.append(f"{label}.max_rounds is allowed only on loop edges")
		else:
			adjacency[source].add(target)
			reverse[target].add(source)
			if edge_type == "data":
				delivered_initial[target].update(consumes)

	if errors:
		return errors

	indegree = {node_id: len(reverse[node_id]) for node_id in node_by_id}
	queue = deque(node_id for node_id, count in indegree.items() if count == 0)
	visited: list[str] = []
	while queue:
		current = queue.popleft()
		visited.append(current)
		for nxt in adjacency[current]:
			indegree[nxt] -= 1
			if indegree[nxt] == 0:
				queue.append(nxt)
	if len(visited) != len(node_by_id):
		errors.append("non-loop edges must form a DAG; cycles require explicit bounded loop edges")

	actual_entries = {node_id for node_id in node_by_id if not reverse[node_id]}
	if set(entry_nodes) != actual_entries:
		errors.append(f"entry_nodes must equal nodes with no incoming non-loop edge: {sorted(actual_entries)}")
	for node_id, node in node_by_id.items():
		if node_id in entry_nodes:
			continue
		missing_inputs = set(node["inputs"]) - delivered_initial[node_id]
		if missing_inputs:
			errors.append(f"node {node_id} has required inputs with no incoming non-loop data edge: {sorted(missing_inputs)}")
	visible = set(entry_nodes)
	queue = deque(entry_nodes)
	while queue:
		current = queue.popleft()
		for nxt in adjacency[current]:
			if nxt not in visible:
				visible.add(nxt)
				queue.append(nxt)
	if visible != set(node_by_id):
		errors.append(f"unreachable nodes: {sorted(set(node_by_id) - visible)}")

	for node_id, node in node_by_id.items():
		incoming = reverse[node_id]
		if len(incoming) > 1 and "join" not in node:
			errors.append(f"fan-in node {node_id} must declare join=all or join=any")
		if len(incoming) <= 1 and "join" in node:
			errors.append(f"node {node_id} declares join without multiple incoming non-loop edges")
		if node["side_effect"] == "consequential":
			if "idempotency_key" not in node:
				errors.append(f"consequential node {node_id} requires an idempotency_key bound to the run and approved artifact")
			if node["max_attempts"] != 1:
				errors.append(f"consequential node {node_id} must set max_attempts to 1; retries require a new human-reviewed attempt")
			approved = any(
				edge["to"] == node_id and edge["type"] == "control" and edge["condition"] == "on_approve"
				and node_by_id[edge["from"]]["kind"] == "human"
				for edge in edges
			)
			if not approved:
				errors.append(f"consequential node {node_id} requires an incoming human on_approve control edge")
			if any(edge["from"] == node_id or edge["to"] == node_id for edge in loop_edges):
				errors.append(f"consequential node {node_id} cannot participate in an automatic loop")

	for edge in loop_edges:
		if not reachable(edge["to"], edge["from"], adjacency):
			errors.append(f"loop edge {edge['from']} -> {edge['to']} must close an existing forward path")

	node_ids = sorted(node_by_id)
	for index, left_id in enumerate(node_ids):
		for right_id in node_ids[index + 1:]:
			if reachable(left_id, right_id, adjacency) or reachable(right_id, left_id, adjacency):
				continue
			left_scopes = node_by_id[left_id]["write_scope"]
			right_scopes = node_by_id[right_id]["write_scope"]
			if any(scope_overlaps(left, right) for left in left_scopes for right in right_scopes):
				errors.append(f"unordered nodes {left_id} and {right_id} have overlapping write_scope")

	minimum_transitions = max(1, len(node_by_id) - len(entry_nodes)) + sum(edge["max_rounds"] for edge in loop_edges)
	if data["max_transitions"] < minimum_transitions:
		errors.append(f"max_transitions must be at least {minimum_transitions} for this graph")
	return errors


def load_graph(path: Path) -> tuple[Any, list[str]]:
	errors: list[str] = []
	try:
		if path.stat().st_size > MAX_BYTES:
			return None, [f"graph exceeds {MAX_BYTES} bytes"]
		data = json.loads(path.read_text(encoding="utf-8"))
	except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
		return None, [f"could not read graph: {exc}"]
	return data, errors


def main() -> int:
	args = parse_args()
	path = Path(args.graph)
	data, errors = load_graph(path)
	if not errors:
		errors = validate_graph(data)
	result = {"ok": not errors, "graph": str(path), "errors": errors}
	if args.json:
		print(json.dumps(result, ensure_ascii=False, indent=2))
	elif errors:
		print("Harness task-graph validation failed:", file=sys.stderr)
		for error in errors:
			print(f"- {error}", file=sys.stderr)
	else:
		print("Harness task-graph validation passed.")
	return 0 if not errors else 1


if __name__ == "__main__":
	raise SystemExit(main())
