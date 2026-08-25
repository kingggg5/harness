#!/usr/bin/env python3
"""Small, fail-closed runtime ledger for Harness task graphs.

This module records claims, outcomes, artifact digests, and recovery decisions. It
does not execute nodes, launch agents, merge code, or authorize side effects.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any

sys.dont_write_bytecode = True

from memory_ops import (
	MemoryErrorWithCode,
	MAX_CLOCK_SKEW_SECONDS,
	assert_current_identity,
	atomic_replace,
	configure_utf8_stdio,
	ensure_within,
	parse_time,
	path_is_link_or_junction,
	pretty_json,
	read_json_bytes,
	read_regular_file_bounded,
	target_file_lock,
	unsafe_reason,
	utc_now,
	validate_identity,
)
from validate_task_graph import (
	load_graph,
	validate_graph,
)


STATE_SCHEMA = 1
MAX_STATE_BYTES = 2 * 1024 * 1024
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
MAX_VERIFY_BYTES = 256 * 1024 * 1024
MAX_GIT_OUTPUT_BYTES = 2 * 1024 * 1024
MAX_EVENTS = 1024
MAX_ARTIFACTS = 512
MAX_NOTE_BYTES = 512
ARTIFACT_PATTERN = re.compile(r"^[a-z][a-z0-9._-]{0,63}$")
COMMIT_PATTERN = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
CLAIM_ID_PATTERN = re.compile(r"^CLM-[0-9a-f]{16}$")
CLAIM_TOKEN_PATTERN = re.compile(r"^tok_[0-9a-f]{64}$")
DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
NODE_STATUSES = {
	"PENDING", "READY", "RUNNING", "SUCCEEDED", "FAILED", "APPROVED",
	"REJECTED", "BLOCKED", "CANCELLED", "SKIPPED",
}
TERMINAL_STATUSES = {"SUCCEEDED", "FAILED", "APPROVED", "REJECTED", "BLOCKED", "CANCELLED", "SKIPPED"}
RUN_STATUSES = {"ACTIVE", "COMPLETE", "BLOCKED", "STOPPED"}
LAST_OUTCOMES = {"", "success", "failure", "approve", "reject", "blocked", "cancelled", "failure-retryable", "stale-ready", "stale-failed", "stale-blocked"}
EVENT_OUTCOMES = LAST_OUTCOMES | {"condition-not-selected"}
OUTCOME_STATUS = {
	"success": "SUCCEEDED",
	"failure": "FAILED",
	"approve": "APPROVED",
	"reject": "REJECTED",
	"blocked": "BLOCKED",
	"cancelled": "CANCELLED",
}
STATE_FIELDS = {
	"schema_version", "graph_digest", "graph_id", "project_id", "run_id",
	"base_revision", "revision", "status", "transition_count", "nodes",
	"artifacts", "loop_rounds", "events", "created_at", "updated_at",
}
NODE_STATE_FIELDS = {
	"status", "activation", "attempts", "claim_id", "claim_digest", "worker",
	"claim_revision", "claimed_at", "updated_at", "last_outcome", "last_event",
}
ARTIFACT_FIELDS = {
	"producer", "activation", "path", "digest", "bytes", "source_revision", "recorded_at",
}
EVENT_FIELDS = {
	"sequence", "type", "node_id", "activation", "attempt", "claim_id",
	"claim_digest", "outcome", "note", "artifacts", "source_revision", "request_digest", "at",
}
EVENT_TYPES = {"start", "claim", "finish", "ready", "skip", "loop-ready", "recover"}


class GraphRuntimeError(RuntimeError):
	def __init__(self, code: str, message: str):
		super().__init__(message)
		self.code = code


def fail(code: str, message: str) -> None:
	raise GraphRuntimeError(code, message)


def add_context_arguments(parser: argparse.ArgumentParser) -> None:
	parser.add_argument("--project", required=True, help="Harness project root")
	parser.add_argument("--graph", required=True, help="Active TASK-GRAPH.json")
	parser.add_argument("--state", help="Optional state file under .harness/.cache")


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Record and resume bounded Harness task-graph execution")
	subparsers = parser.add_subparsers(dest="command", required=True)

	start = subparsers.add_parser("start", help="Bind a validated graph to its exact clean Git baseline")
	add_context_arguments(start)
	start.add_argument("--artifact", action="append", default=[], help="Seed input as name=project-relative-file")

	status = subparsers.add_parser("status", help="Read current state without mutation")
	add_context_arguments(status)
	status.add_argument("--verify-artifacts", action="store_true", help="Re-hash all current artifacts")

	resume = subparsers.add_parser("resume", help="Fail closed unless Git ancestry and every artifact still verify")
	add_context_arguments(resume)

	claim = subparsers.add_parser("claim", help="Lease one ready node to a worker")
	add_context_arguments(claim)
	claim.add_argument("--node", required=True)
	claim.add_argument("--worker", required=True)
	claim.add_argument("--workspace-revision", help="Exact worker baseline; defaults to current HEAD")
	claim.add_argument("--expected-revision", required=True, type=int)

	finish = subparsers.add_parser("finish", help="Record one claimed node outcome and its evidence")
	add_context_arguments(finish)
	finish.add_argument("--node", required=True)
	finish.add_argument("--claim-token", help="Lease token; prefer ephemeral HARNESS_GRAPH_CLAIM_TOKEN to avoid shell history")
	finish.add_argument("--outcome", required=True, choices=sorted(OUTCOME_STATUS))
	finish.add_argument("--retry", action="store_true", help="Return a failed node to READY when attempts remain")
	finish.add_argument("--artifact", action="append", default=[], help="Output as name=project-relative-file")
	finish.add_argument("--source-revision", help="Exact result commit; required for successful writing nodes")
	finish.add_argument("--note", default="", help="Optional sanitized one-line receipt note")
	finish.add_argument("--expected-revision", required=True, type=int)

	recover = subparsers.add_parser("recover", help="Resolve a timed-out claim without deleting worker files")
	add_context_arguments(recover)
	recover.add_argument("--node", required=True)
	recover.add_argument("--claim-id", required=True)
	recover.add_argument("--action", required=True, choices=("ready", "failed", "blocked"))
	recover.add_argument("--note", required=True)
	recover.add_argument("--expected-revision", required=True, type=int)
	return parser.parse_args()


def canonical_json(data: Any) -> bytes:
	return (json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def digest_bytes(data: bytes) -> str:
	return f"sha256:{hashlib.sha256(data).hexdigest()}"


def pattern_matches(pattern: re.Pattern[str], value: Any) -> bool:
	return isinstance(value, str) and pattern.fullmatch(value) is not None


def valid_timestamp(value: Any, now_limit: datetime) -> bool:
	if not isinstance(value, str):
		return False
	try:
		return parse_time(value) <= now_limit
	except MemoryErrorWithCode:
		return False


def graph_digest(graph: dict[str, Any]) -> str:
	return digest_bytes(canonical_json(graph))


def normalized_note(value: str, field: str) -> str:
	if not isinstance(value, str):
		fail("INVALID_FIELD", f"{field} must be a string")
	normalized = " ".join(value.strip().split())
	if len(normalized.encode("utf-8")) > MAX_NOTE_BYTES:
		fail("FIELD_TOO_LARGE", f"{field} exceeds {MAX_NOTE_BYTES} UTF-8 bytes")
	unsafe = unsafe_reason(normalized) if normalized else None
	if unsafe:
		fail("UNSAFE_RECEIPT", f"{field} contains {unsafe}; store it in a bounded evidence file instead")
	return normalized


def claim_token_value(supplied: str | None) -> str:
	environment = os.environ.get("HARNESS_GRAPH_CLAIM_TOKEN", "")
	if supplied and environment and supplied != environment:
		fail("CLAIM_TOKEN_CONFLICT", "CLI and HARNESS_GRAPH_CLAIM_TOKEN values differ")
	token = supplied or environment
	if not pattern_matches(CLAIM_TOKEN_PATTERN, token):
		fail("CLAIM_TOKEN_INVALID", "Provide the exact lease token through HARNESS_GRAPH_CLAIM_TOKEN or --claim-token")
	return token


def run_git(project: Path, arguments: list[str], *, allow_failure: bool = False) -> tuple[int, bytes, bytes]:
	with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
		try:
			result = subprocess.run(
				["git", "-C", str(project), *arguments],
				stdout=stdout_file,
				stderr=stderr_file,
				timeout=20,
				check=False,
			)
		except (OSError, subprocess.TimeoutExpired) as exc:
			fail("GIT_UNAVAILABLE", f"Git command failed to start or timed out: {exc}")
		stdout_size = stdout_file.tell()
		stderr_size = stderr_file.tell()
		if stdout_size > MAX_GIT_OUTPUT_BYTES or stderr_size > MAX_GIT_OUTPUT_BYTES:
			fail("GIT_OUTPUT_TOO_LARGE", f"Git output exceeded {MAX_GIT_OUTPUT_BYTES} bytes")
		stdout_file.seek(0)
		stderr_file.seek(0)
		stdout = stdout_file.read()
		stderr = stderr_file.read()
	if result.returncode != 0 and not allow_failure:
		detail = stderr.decode("utf-8", errors="replace").strip()[:1000]
		fail("GIT_FAILED", detail or f"Git exited {result.returncode}: {' '.join(arguments[:3])}")
	return result.returncode, stdout, stderr


def git_text(project: Path, arguments: list[str]) -> str:
	_, stdout, _ = run_git(project, arguments)
	try:
		return stdout.decode("utf-8").strip()
	except UnicodeDecodeError as exc:
		fail("GIT_NON_UTF8", "Git returned a non-UTF-8 identifier")
		raise AssertionError from exc


def verify_commit(project: Path, revision: str, field: str) -> str:
	if not isinstance(revision, str) or not COMMIT_PATTERN.fullmatch(revision):
		fail("INVALID_REVISION", f"{field} must be an exact lowercase 40/64-character commit ID")
	resolved = git_text(project, ["rev-parse", "--verify", f"{revision}^{{commit}}"])
	if resolved != revision:
		fail("REVISION_MISMATCH", f"{field} resolved to {resolved}, not the recorded exact commit")
	return resolved


def require_ancestor(project: Path, ancestor: str, descendant: str) -> None:
	code, _, _ = run_git(project, ["merge-base", "--is-ancestor", ancestor, descendant], allow_failure=True)
	if code != 0:
		fail("REVISION_DIVERGED", f"{descendant} is not descended from required baseline {ancestor}")


def git_paths(project: Path, arguments: list[str]) -> list[str]:
	_, stdout, _ = run_git(project, arguments)
	try:
		paths = [item.decode("utf-8") for item in stdout.split(b"\0") if item]
	except UnicodeDecodeError as exc:
		fail("GIT_NON_UTF8", "Git path output is not UTF-8")
		raise AssertionError from exc
	return paths


def outside_harness(paths: list[str]) -> list[str]:
	return sorted(path for path in paths if path != ".harness" and not path.startswith(".harness/"))


def verify_start_baseline(project: Path, base_revision: str) -> None:
	verify_commit(project, base_revision, "base_revision")
	head = git_text(project, ["rev-parse", "HEAD"])
	if head != base_revision:
		fail("BASE_NOT_HEAD", f"Graph base {base_revision} does not equal current HEAD {head}")
	tracked = git_paths(project, ["diff", "--name-only", "-z", "--relative", base_revision, "--", "."])
	untracked = git_paths(project, ["ls-files", "--others", "--exclude-standard", "-z", "--", "."])
	dirty = outside_harness([*tracked, *untracked])
	if dirty:
		fail("DIRTY_BASELINE", f"Start requires no source changes outside .harness; found {dirty[:10]}")


def verify_runtime_ancestry(project: Path, base_revision: str) -> str:
	verify_commit(project, base_revision, "base_revision")
	head = verify_commit(project, git_text(project, ["rev-parse", "HEAD"]), "HEAD")
	require_ancestor(project, base_revision, head)
	return head


def changed_paths(project: Path, before: str, after: str) -> list[str]:
	require_ancestor(project, before, after)
	return git_paths(project, ["diff", "--name-only", "-z", "--relative", before, after, "--", "."])


def path_in_scopes(path: str, scopes: list[str]) -> bool:
	return any(scope == "." or path == scope or path.startswith(f"{scope}/") for scope in scopes)


def verify_changed_scope(project: Path, before: str, after: str, scopes: list[str]) -> list[str]:
	paths = changed_paths(project, before, after)
	violations = sorted(path for path in paths if not path_in_scopes(path, scopes))
	if violations:
		fail("WRITE_SCOPE_VIOLATION", f"Result commit changes paths outside node write_scope: {violations[:20]}")
	return sorted(paths)


def resolve_project(value: str) -> Path:
	try:
		project = Path(value).expanduser().resolve(strict=True)
	except OSError as exc:
		fail("PROJECT_UNAVAILABLE", f"Cannot resolve project: {exc}")
	if not project.is_dir() or path_is_link_or_junction(project):
		fail("PROJECT_INVALID", f"Project must be a real directory: {project}")
	return project


def verify_project_binding(project: Path, graph: dict[str, Any]) -> None:
	harness = project / ".harness"
	if not harness.is_dir() or path_is_link_or_junction(harness):
		fail("HARNESS_ROOT_INVALID", f".harness must be a real project directory: {harness}")
	identity, _ = read_json_bytes(harness / "IDENTITY.json")
	identity_errors = validate_identity(identity)
	if identity_errors:
		fail("IDENTITY_INVALID", "; ".join(identity_errors))
	assert_current_identity(project, identity, str(identity["logical_scope"]))
	if identity["project_id"] != graph["project_id"]:
		fail("PROJECT_MISMATCH", "Graph Project ID does not match .harness/IDENTITY.json")
	run_state, _ = read_json_bytes(harness / "STATE.json")
	if run_state.get("project_id") != graph["project_id"] or run_state.get("run_id") != graph["run_id"]:
		fail("RUN_MISMATCH", "Graph Project ID/Run ID do not match active .harness/STATE.json")
	if run_state.get("operation") not in {"start", "resume"}:
		fail("RUN_INACTIVE", "Graph runtime requires STATE.json operation start or resume")


def resolve_graph(project: Path, value: str) -> tuple[Path, dict[str, Any], str]:
	path = Path(value).expanduser()
	if not path.is_absolute():
		path = project / path
	path = path.absolute()
	ensure_within(path, project, "task graph")
	if path_is_link_or_junction(path):
		fail("GRAPH_LINKED", f"Task graph cannot be a symlink or junction: {path}")
	data, errors = load_graph(path)
	if not errors:
		errors = validate_graph(data)
	if errors:
		fail("GRAPH_INVALID", "; ".join(errors))
	if not data.get("project_id") or not data.get("run_id"):
		fail("GRAPH_INACTIVE", "Runtime requires an active graph with Project ID and Run ID")
	verify_project_binding(project, data)
	return path, data, graph_digest(data)


def default_state_path(project: Path, graph: dict[str, Any]) -> Path:
	key = digest_bytes(f"{graph['project_id']}\0{graph['run_id']}\0{graph['graph_id']}".encode("utf-8"))[7:23]
	return project / ".harness" / ".cache" / "graph-runs" / f"{graph['graph_id']}-{key}.json"


def resolve_state_path(project: Path, graph: dict[str, Any], supplied: str | None) -> Path:
	cache_root = project / ".harness" / ".cache"
	cache_root.mkdir(parents=True, exist_ok=True)
	if path_is_link_or_junction(cache_root):
		fail("STATE_ROOT_LINKED", f"Graph state root cannot be linked: {cache_root}")
	path = default_state_path(project, graph) if not supplied else Path(supplied).expanduser()
	if not path.is_absolute():
		path = project / path
	path = path.absolute()
	ensure_within(path, cache_root, "graph runtime state")
	if path_is_link_or_junction(path):
		fail("STATE_LINKED", f"Graph state cannot be linked: {path}")
	return path


def safe_artifact_path(project: Path, relative: str) -> Path:
	if "\\" in relative or not relative or PurePosixPath(relative).is_absolute() or ".." in PurePosixPath(relative).parts:
		fail("ARTIFACT_PATH_INVALID", f"Artifact path must be a safe project-relative POSIX path: {relative!r}")
	path = (project / PurePosixPath(relative)).absolute()
	ensure_within(path, project, "artifact")
	current = path.parent
	while current != project:
		if current.exists() and path_is_link_or_junction(current):
			fail("ARTIFACT_PATH_LINKED", f"Artifact parent is a symlink or junction: {current}")
		current = current.parent
	return path


def parse_artifact_specs(project: Path, specs: list[str]) -> dict[str, tuple[str, bytes]]:
	result: dict[str, tuple[str, bytes]] = {}
	for spec in specs:
		if "=" not in spec:
			fail("ARTIFACT_SPEC_INVALID", f"Artifact must use name=project-relative-file: {spec!r}")
		name, relative = spec.split("=", 1)
		if not ARTIFACT_PATTERN.fullmatch(name):
			fail("ARTIFACT_NAME_INVALID", f"Artifact name is invalid: {name!r}")
		if name in result:
			fail("ARTIFACT_DUPLICATE", f"Artifact supplied more than once: {name}")
		path = safe_artifact_path(project, relative)
		try:
			data = read_regular_file_bounded(path, MAX_ARTIFACT_BYTES, f"artifact {name}")
		except OSError as exc:
			fail("ARTIFACT_UNAVAILABLE", f"Cannot read artifact {name}: {exc}")
		result[name] = (PurePosixPath(relative).as_posix(), data)
	return result


def artifact_record(name: str, relative: str, data: bytes, producer: str, activation: int, source_revision: str) -> dict[str, Any]:
	return {
		"producer": producer,
		"activation": activation,
		"path": relative,
		"digest": digest_bytes(data),
		"bytes": len(data),
		"source_revision": source_revision,
		"recorded_at": utc_now(),
	}


def verify_artifact(project: Path, name: str, record: dict[str, Any]) -> None:
	path = safe_artifact_path(project, record["path"])
	try:
		data = read_regular_file_bounded(path, MAX_ARTIFACT_BYTES, f"artifact {name}")
	except OSError as exc:
		fail("ARTIFACT_UNAVAILABLE", f"Cannot read artifact {name}: {exc}")
	if len(data) != record["bytes"] or digest_bytes(data) != record["digest"]:
		fail("ARTIFACT_DRIFT", f"Artifact changed after receipt: {name} ({record['path']})")


def verify_all_artifacts(project: Path, state: dict[str, Any]) -> None:
	total = sum(record["bytes"] for record in state["artifacts"].values())
	if total > MAX_VERIFY_BYTES:
		fail("VERIFY_BUDGET_EXCEEDED", f"Current artifacts total {total} bytes; verification limit is {MAX_VERIFY_BYTES}")
	for name, record in state["artifacts"].items():
		verify_artifact(project, name, record)


def verify_recorded_revisions(project: Path, state: dict[str, Any]) -> None:
	base = state["base_revision"]
	for name, record in state["artifacts"].items():
		verify_commit(project, record["source_revision"], f"artifact {name} source_revision")
		require_ancestor(project, base, record["source_revision"])
	for node_id, item in state["nodes"].items():
		if item["status"] == "RUNNING":
			verify_commit(project, item["claim_revision"], f"node {node_id} claim_revision")
			require_ancestor(project, base, item["claim_revision"])


def condition_matches(condition: str, status: str) -> bool:
	if condition == "on_success":
		return status == "SUCCEEDED"
	if condition == "on_failure":
		return status == "FAILED"
	if condition == "on_approve":
		return status == "APPROVED"
	if condition == "on_reject":
		return status == "REJECTED"
	return status in {"SUCCEEDED", "FAILED", "APPROVED", "REJECTED"}


def append_event(
	state: dict[str, Any], event_type: str, *, node_id: str = "", activation: int = 0,
	attempt: int = 0, claim_id: str = "", claim_digest: str = "", outcome: str = "",
	note: str = "", artifacts: dict[str, str] | None = None, source_revision: str = "",
	request_digest: str = "",
) -> int:
	if len(state["events"]) >= MAX_EVENTS:
		fail("EVENT_LIMIT", f"Graph runtime event limit {MAX_EVENTS} reached")
	sequence = len(state["events"])
	state["events"].append({
		"sequence": sequence,
		"type": event_type,
		"node_id": node_id,
		"activation": activation,
		"attempt": attempt,
		"claim_id": claim_id,
		"claim_digest": claim_digest,
		"outcome": outcome,
		"note": note,
		"artifacts": artifacts or {},
		"source_revision": source_revision,
		"request_digest": request_digest,
		"at": utc_now(),
	})
	return sequence


def initial_node_state(ready: bool) -> dict[str, Any]:
	now = utc_now()
	return {
		"status": "READY" if ready else "PENDING",
		"activation": 1 if ready else 0,
		"attempts": 0,
		"claim_id": "",
		"claim_digest": "",
		"worker": "",
		"claim_revision": "",
		"claimed_at": "",
		"updated_at": now,
		"last_outcome": "",
		"last_event": 0,
	}


def new_state(graph: dict[str, Any], digest: str, artifacts: dict[str, dict[str, Any]]) -> dict[str, Any]:
	now = utc_now()
	state = {
		"schema_version": STATE_SCHEMA,
		"graph_digest": digest,
		"graph_id": graph["graph_id"],
		"project_id": graph["project_id"],
		"run_id": graph["run_id"],
		"base_revision": graph["base_revision"],
		"revision": 0,
		"status": "ACTIVE",
		"transition_count": 0,
		"nodes": {node["id"]: initial_node_state(node["id"] in graph["entry_nodes"]) for node in graph["nodes"]},
		"artifacts": artifacts,
		"loop_rounds": {f"{edge['from']}->{edge['to']}": 0 for edge in graph["edges"] if edge["type"] == "loop"},
		"events": [],
		"created_at": now,
		"updated_at": now,
	}
	append_event(state, "start", note="graph runtime bound to exact baseline", source_revision=graph["base_revision"])
	return state


def node_map(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
	return {node["id"]: node for node in graph["nodes"]}


def edge_group_matches(state: dict[str, Any], edges: list[dict[str, Any]]) -> bool:
	source = edges[0]["from"]
	source_state = state["nodes"][source]
	if not all(condition_matches(edge["condition"], source_state["status"]) for edge in edges):
		return False
	for edge in edges:
		if edge["type"] != "data":
			continue
		for artifact in edge["consumes"]:
			record = state["artifacts"].get(artifact)
			if not record or record["producer"] != source or record["activation"] != source_state["activation"]:
				return False
	return True


def refresh_nonloop_nodes(state: dict[str, Any], graph: dict[str, Any]) -> None:
	incoming: dict[str, dict[str, list[dict[str, Any]]]] = {}
	for edge in graph["edges"]:
		if edge["type"] == "loop":
			continue
		incoming.setdefault(edge["to"], {}).setdefault(edge["from"], []).append(edge)
	changed = True
	while changed:
		changed = False
		for node in graph["nodes"]:
			node_id = node["id"]
			runtime = state["nodes"][node_id]
			if runtime["status"] not in {"PENDING", "SKIPPED"} or runtime["activation"] != 0:
				continue
			groups = incoming.get(node_id, {})
			if not groups:
				continue
			matches = [edge_group_matches(state, edges) for edges in groups.values()]
			terminal = [state["nodes"][source]["status"] in TERMINAL_STATUSES for source in groups]
			ready = any(matches) if node.get("join") == "any" else all(matches)
			impossible = all(terminal) and not ready if node.get("join") == "any" else any(done and not match for done, match in zip(terminal, matches))
			if ready:
				runtime["status"] = "READY"
				runtime["activation"] = 1
				runtime["attempts"] = 0
				runtime["updated_at"] = utc_now()
				runtime["last_event"] = append_event(state, "ready", node_id=node_id, activation=1)
				changed = True
			elif impossible and runtime["status"] != "SKIPPED":
				runtime["status"] = "SKIPPED"
				runtime["updated_at"] = utc_now()
				runtime["last_event"] = append_event(state, "skip", node_id=node_id, outcome="condition-not-selected")
				changed = True


def activate_loops(state: dict[str, Any], graph: dict[str, Any], source_id: str) -> None:
	for edge in graph["edges"]:
		if edge["type"] != "loop" or edge["from"] != source_id:
			continue
		source_state = state["nodes"][source_id]
		if not condition_matches(edge["condition"], source_state["status"]):
			continue
		key = f"{edge['from']}->{edge['to']}"
		if state["loop_rounds"][key] >= edge["max_rounds"]:
			continue
		target = state["nodes"][edge["to"]]
		if target["status"] not in TERMINAL_STATUSES:
			fail("LOOP_TARGET_ACTIVE", f"Loop target {edge['to']} is not terminal")
		state["loop_rounds"][key] += 1
		target["status"] = "READY"
		target["activation"] += 1
		target["attempts"] = 0
		target["claim_id"] = ""
		target["claim_digest"] = ""
		target["worker"] = ""
		target["claim_revision"] = ""
		target["claimed_at"] = ""
		target["updated_at"] = utc_now()
		target["last_outcome"] = ""
		target["last_event"] = append_event(
			state, "loop-ready", node_id=edge["to"], activation=target["activation"],
			note=f"{key} round {state['loop_rounds'][key]}",
		)


def derive_run_status(state: dict[str, Any], graph: dict[str, Any]) -> str:
	statuses = [item["status"] for item in state["nodes"].values()]
	if any(status in {"READY", "RUNNING"} for status in statuses):
		return "ACTIVE"
	if any(status == "PENDING" for status in statuses):
		return "BLOCKED"
	outgoing = {edge["from"] for edge in graph["edges"]}
	sinks = [node["id"] for node in graph["nodes"] if node["id"] not in outgoing]
	if any(state["nodes"][node_id]["status"] in {"SUCCEEDED", "APPROVED"} for node_id in sinks):
		return "COMPLETE"
	return "STOPPED"


def validate_state(state: Any, graph: dict[str, Any], expected_digest: str) -> list[str]:
	errors: list[str] = []
	now_limit = parse_time(utc_now()) + timedelta(seconds=MAX_CLOCK_SKEW_SECONDS)
	if not isinstance(state, dict):
		return ["state root must be an object"]
	if set(state) != STATE_FIELDS:
		errors.append(f"state fields differ from schema: missing={sorted(STATE_FIELDS - set(state))} unknown={sorted(set(state) - STATE_FIELDS)}")
		return errors
	if state["schema_version"] != STATE_SCHEMA:
		errors.append(f"state schema_version must be {STATE_SCHEMA}")
	for field in ("graph_id", "project_id", "run_id", "base_revision"):
		if state[field] != graph[field]:
			errors.append(f"state {field} does not match graph")
	if state["graph_digest"] != expected_digest:
		errors.append("graph changed after runtime start")
	if not isinstance(state["revision"], int) or isinstance(state["revision"], bool) or state["revision"] < 0:
		errors.append("revision must be a non-negative integer")
	if not isinstance(state["status"], str) or state["status"] not in RUN_STATUSES:
		errors.append(f"status must be one of {sorted(RUN_STATUSES)}")
	if not isinstance(state["transition_count"], int) or isinstance(state["transition_count"], bool) or not 0 <= state["transition_count"] <= graph["max_transitions"]:
		errors.append("transition_count is outside the graph budget")
	event_count = len(state["events"]) if isinstance(state["events"], list) else 0
	if not isinstance(state["nodes"], dict) or set(state["nodes"]) != set(node_map(graph)):
		errors.append("state nodes do not exactly match graph nodes")
	else:
		for node in graph["nodes"]:
			node_id = node["id"]
			item = state["nodes"][node_id]
			if not isinstance(item, dict) or set(item) != NODE_STATE_FIELDS:
				errors.append(f"node state {node_id} has invalid fields")
				continue
			if not isinstance(item["status"], str) or item["status"] not in NODE_STATUSES:
				errors.append(f"node state {node_id} has invalid status")
			if not isinstance(item["activation"], int) or isinstance(item["activation"], bool) or not 0 <= item["activation"] <= graph["max_transitions"] + 1:
				errors.append(f"node state {node_id} has invalid activation")
			if not isinstance(item["attempts"], int) or isinstance(item["attempts"], bool) or not 0 <= item["attempts"] <= node["max_attempts"]:
				errors.append(f"node state {node_id} has invalid attempts")
			if any(not isinstance(item[field], str) for field in ("claim_id", "claim_digest", "worker", "claim_revision", "claimed_at", "updated_at", "last_outcome")):
				errors.append(f"node state {node_id} has non-string metadata")
			if isinstance(item["last_outcome"], str) and item["last_outcome"] not in LAST_OUTCOMES:
				errors.append(f"node state {node_id} has invalid last_outcome")
			if isinstance(item["worker"], str) and item["worker"] and unsafe_reason(item["worker"]):
				errors.append(f"node state {node_id} has unsafe worker metadata")
			if item["status"] == "RUNNING":
				if not pattern_matches(CLAIM_ID_PATTERN, item["claim_id"]) or not pattern_matches(DIGEST_PATTERN, item["claim_digest"]) or not pattern_matches(COMMIT_PATTERN, item["claim_revision"]):
					errors.append(f"running node {node_id} has invalid claim metadata")
				if not valid_timestamp(item["claimed_at"], now_limit):
					errors.append(f"running node {node_id} has invalid claimed_at")
			elif any(item[field] for field in ("claim_id", "claim_digest", "worker", "claim_revision", "claimed_at")):
				errors.append(f"non-running node {node_id} retains claim metadata")
			if not isinstance(item["last_event"], int) or isinstance(item["last_event"], bool) or not 0 <= item["last_event"] < event_count:
				errors.append(f"node state {node_id} has invalid last_event")
			if not valid_timestamp(item["updated_at"], now_limit):
				errors.append(f"node state {node_id} has invalid updated_at")
	if not isinstance(state["artifacts"], dict) or len(state["artifacts"]) > MAX_ARTIFACTS:
		errors.append("artifacts must be a bounded object")
	else:
		for name, record in state["artifacts"].items():
			if not pattern_matches(ARTIFACT_PATTERN, name) or not isinstance(record, dict) or set(record) != ARTIFACT_FIELDS:
				errors.append(f"artifact record is invalid: {name!r}")
				continue
			if not isinstance(record["producer"], str) or (record["producer"] != "__input__" and record["producer"] not in node_map(graph)):
				errors.append(f"artifact {name} has unknown producer")
			if not isinstance(record["activation"], int) or isinstance(record["activation"], bool) or record["activation"] < 0:
				errors.append(f"artifact {name} has invalid activation")
			if not pattern_matches(DIGEST_PATTERN, record["digest"]):
				errors.append(f"artifact {name} has invalid digest")
			if not isinstance(record["bytes"], int) or isinstance(record["bytes"], bool) or not 0 <= record["bytes"] <= MAX_ARTIFACT_BYTES:
				errors.append(f"artifact {name} has invalid byte size")
			if not pattern_matches(COMMIT_PATTERN, record["source_revision"]):
				errors.append(f"artifact {name} has invalid source revision")
			if not isinstance(record["path"], str) or not record["path"] or "\\" in record["path"] or PurePosixPath(record["path"]).is_absolute() or ".." in PurePosixPath(record["path"]).parts:
				errors.append(f"artifact {name} has invalid path")
			if not valid_timestamp(record["recorded_at"], now_limit):
				errors.append(f"artifact {name} has invalid recorded_at")
	if not isinstance(state["loop_rounds"], dict):
		errors.append("loop_rounds must be an object")
	else:
		expected_loops = {f"{edge['from']}->{edge['to']}": edge["max_rounds"] for edge in graph["edges"] if edge["type"] == "loop"}
		if set(state["loop_rounds"]) != set(expected_loops):
			errors.append("loop_rounds keys do not match graph loops")
		for key, count in state["loop_rounds"].items():
			if key in expected_loops and (not isinstance(count, int) or isinstance(count, bool) or not 0 <= count <= expected_loops[key]):
				errors.append(f"loop round count is invalid: {key}")
	if not isinstance(state["events"], list) or not 1 <= len(state["events"]) <= MAX_EVENTS:
		errors.append("events must be a bounded non-empty array")
	else:
		for sequence, event in enumerate(state["events"]):
			if not isinstance(event, dict) or set(event) != EVENT_FIELDS or event.get("sequence") != sequence:
				errors.append(f"event {sequence} is invalid")
				break
			if not isinstance(event["type"], str) or event["type"] not in EVENT_TYPES or not isinstance(event["node_id"], str) or (event["node_id"] and event["node_id"] not in node_map(graph)):
				errors.append(f"event {sequence} has invalid type or node")
			if not isinstance(event["activation"], int) or isinstance(event["activation"], bool) or event["activation"] < 0:
				errors.append(f"event {sequence} has invalid activation")
			if not isinstance(event["attempt"], int) or isinstance(event["attempt"], bool) or event["attempt"] < 0:
				errors.append(f"event {sequence} has invalid attempt")
			if event["claim_id"] and not pattern_matches(CLAIM_ID_PATTERN, event["claim_id"]):
				errors.append(f"event {sequence} has invalid claim_id")
			for field in ("claim_digest", "request_digest"):
				if event[field] and not pattern_matches(DIGEST_PATTERN, event[field]):
					errors.append(f"event {sequence} has invalid {field}")
			if event["source_revision"] and not pattern_matches(COMMIT_PATTERN, event["source_revision"]):
				errors.append(f"event {sequence} has invalid source_revision")
			if not isinstance(event["outcome"], str) or event["outcome"] not in EVENT_OUTCOMES:
				errors.append(f"event {sequence} has invalid outcome")
			if not isinstance(event["note"], str) or len(event["note"].encode("utf-8")) > MAX_NOTE_BYTES or (event["note"] and unsafe_reason(event["note"])):
				errors.append(f"event {sequence} has invalid note")
			if not isinstance(event["artifacts"], dict) or len(event["artifacts"]) > 64 or any(not pattern_matches(ARTIFACT_PATTERN, name) or not pattern_matches(DIGEST_PATTERN, value) for name, value in event["artifacts"].items()):
				errors.append(f"event {sequence} has invalid artifact digests")
			if not valid_timestamp(event["at"], now_limit):
				errors.append(f"event {sequence} has invalid timestamp")
		if isinstance(state["revision"], int) and not isinstance(state["revision"], bool) and state["revision"] > len(state["events"]) - 1:
			errors.append("revision exceeds recorded mutation events")
		if isinstance(state["transition_count"], int) and not isinstance(state["transition_count"], bool):
			actual_transitions = sum(1 for event in state["events"] if isinstance(event, dict) and event.get("type") in {"finish", "recover"})
			if state["transition_count"] != actual_transitions:
				errors.append("transition_count does not match finish/recover events")
		if isinstance(state["nodes"], dict):
			for node_id, item in state["nodes"].items():
				if not isinstance(item, dict) or not isinstance(item.get("last_event"), int) or isinstance(item.get("last_event"), bool) or not 0 <= item["last_event"] < len(state["events"]):
					continue
				last_event = state["events"][item["last_event"]]
				if item["last_event"] != 0 and isinstance(last_event, dict) and last_event.get("node_id") != node_id:
					errors.append(f"node state {node_id} last_event belongs to another node")
				if item.get("status") == "RUNNING" and isinstance(last_event, dict) and (last_event.get("type") != "claim" or last_event.get("claim_id") != item.get("claim_id") or last_event.get("claim_digest") != item.get("claim_digest")):
					errors.append(f"running node {node_id} does not match its claim event")
	try:
		if derive_run_status(state, graph) != state["status"]:
			errors.append("stored run status does not match node states")
	except (KeyError, TypeError):
		pass
	for field in ("created_at", "updated_at"):
		if not valid_timestamp(state[field], now_limit):
			errors.append(f"state {field} is invalid")
	if valid_timestamp(state["created_at"], now_limit) and valid_timestamp(state["updated_at"], now_limit) and parse_time(state["updated_at"]) < parse_time(state["created_at"]):
		errors.append("state updated_at precedes created_at")
	return errors


def read_state(path: Path, graph: dict[str, Any], expected_digest: str) -> tuple[dict[str, Any], bytes]:
	try:
		raw = read_regular_file_bounded(path, MAX_STATE_BYTES, "graph runtime state")
	except OSError as exc:
		fail("STATE_UNAVAILABLE", f"Cannot read graph runtime state: {exc}")
	try:
		state = json.loads(raw.decode("utf-8"))
	except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, MemoryError) as exc:
		fail("STATE_INVALID", f"Graph runtime state is invalid JSON: {exc}")
	errors = validate_state(state, graph, expected_digest)
	if errors:
		fail("STATE_INVALID", "; ".join(errors))
	return state, raw


def require_revision(state: dict[str, Any], expected: int) -> None:
	if expected != state["revision"]:
		fail("REVISION_CONFLICT", f"Expected state revision {expected}, current revision is {state['revision']}")


def persist_state(path: Path, state: dict[str, Any], graph: dict[str, Any], digest: str, expected: bytes) -> None:
	state["revision"] += 1
	state["updated_at"] = utc_now()
	state["status"] = derive_run_status(state, graph)
	errors = validate_state(state, graph, digest)
	if errors:
		fail("STATE_INVALID_AFTER_MUTATION", "; ".join(errors))
	atomic_replace(path, pretty_json(state), expected=expected)


def stale_nodes(state: dict[str, Any], graph: dict[str, Any]) -> list[dict[str, Any]]:
	now = datetime.now(timezone.utc)
	result: list[dict[str, Any]] = []
	for node in graph["nodes"]:
		item = state["nodes"][node["id"]]
		if item["status"] != "RUNNING":
			continue
		claimed = parse_time(item["claimed_at"])
		age = max(0, int((now - claimed).total_seconds()))
		if age >= node["timeout_seconds"]:
			result.append({"node": node["id"], "claim_id": item["claim_id"], "age_seconds": age, "timeout_seconds": node["timeout_seconds"]})
	return result


def state_summary(state: dict[str, Any], graph: dict[str, Any], path: Path) -> dict[str, Any]:
	return {
		"ok": True,
		"result": "GRAPH_STATE",
		"state_path": str(path),
		"graph_id": state["graph_id"],
		"project_id": state["project_id"],
		"run_id": state["run_id"],
		"revision": state["revision"],
		"status": state["status"],
		"transition_count": state["transition_count"],
		"max_transitions": graph["max_transitions"],
		"ready": sorted(node_id for node_id, item in state["nodes"].items() if item["status"] == "READY"),
		"running": sorted(
			({"node": node_id, "claim_id": item["claim_id"], "worker": item["worker"], "workspace_revision": item["claim_revision"]} for node_id, item in state["nodes"].items() if item["status"] == "RUNNING"),
			key=lambda item: item["node"],
		),
		"stale": stale_nodes(state, graph),
		"nodes": {node_id: {"status": item["status"], "activation": item["activation"], "attempts": item["attempts"], "last_outcome": item["last_outcome"]} for node_id, item in sorted(state["nodes"].items())},
		"artifacts": {name: {"digest": record["digest"], "path": record["path"], "producer": record["producer"], "source_revision": record["source_revision"]} for name, record in sorted(state["artifacts"].items())},
		"loop_rounds": state["loop_rounds"],
	}


def load_context(args: argparse.Namespace) -> tuple[Path, dict[str, Any], str, Path]:
	project = resolve_project(args.project)
	_, graph, digest = resolve_graph(project, args.graph)
	state_path = resolve_state_path(project, graph, args.state)
	return project, graph, digest, state_path


def start_runtime(args: argparse.Namespace) -> dict[str, Any]:
	project, graph, digest, state_path = load_context(args)
	with target_file_lock(state_path):
		verify_project_binding(project, graph)
		verify_start_baseline(project, graph["base_revision"])
		supplied = parse_artifact_specs(project, args.artifact)
		produced = {artifact for node in graph["nodes"] for artifact in node["outputs"]}
		required_inputs = {artifact for node in graph["nodes"] if node["id"] in graph["entry_nodes"] for artifact in node["inputs"] if artifact not in produced}
		optional_inputs = {artifact for node in graph["nodes"] if node["id"] in graph["entry_nodes"] for artifact in node["optional_inputs"] if artifact not in produced}
		if not required_inputs.issubset(supplied) or not set(supplied).issubset(required_inputs | optional_inputs):
			fail("INITIAL_ARTIFACT_MISMATCH", f"Initial artifacts require {sorted(required_inputs)} and may include {sorted(optional_inputs)}; received {sorted(supplied)}")
		artifacts = {
			name: artifact_record(name, relative, data, "__input__", 0, graph["base_revision"])
			for name, (relative, data) in supplied.items()
		}
		state = new_state(graph, digest, artifacts)
		state["status"] = derive_run_status(state, graph)
		errors = validate_state(state, graph, digest)
		if errors:
			fail("STATE_INVALID_AFTER_MUTATION", "; ".join(errors))
		atomic_replace(state_path, pretty_json(state), expected=None)
		result = state_summary(state, graph, state_path)
		result["result"] = "GRAPH_STARTED"
		return result


def status_runtime(args: argparse.Namespace, *, resume: bool = False) -> dict[str, Any]:
	project, graph, digest, state_path = load_context(args)
	state, _ = read_state(state_path, graph, digest)
	verify_runtime_ancestry(project, graph["base_revision"])
	if resume or getattr(args, "verify_artifacts", False):
		verify_all_artifacts(project, state)
	if resume:
		verify_recorded_revisions(project, state)
	result = state_summary(state, graph, state_path)
	result["result"] = "GRAPH_RESUMABLE" if resume else "GRAPH_STATE"
	result["artifacts_verified"] = bool(resume or getattr(args, "verify_artifacts", False))
	return result


def claim_runtime(args: argparse.Namespace) -> dict[str, Any]:
	project, graph, digest, state_path = load_context(args)
	worker = normalized_note(args.worker, "worker")
	if not worker:
		fail("WORKER_REQUIRED", "worker must not be empty")
	with target_file_lock(state_path):
		verify_project_binding(project, graph)
		state, raw = read_state(state_path, graph, digest)
		require_revision(state, args.expected_revision)
		if state["transition_count"] >= graph["max_transitions"]:
			fail("TRANSITION_LIMIT", "Graph transition budget is exhausted")
		nodes = node_map(graph)
		if args.node not in nodes:
			fail("NODE_UNKNOWN", f"Unknown graph node: {args.node}")
		node = nodes[args.node]
		runtime = state["nodes"][args.node]
		if runtime["status"] != "READY":
			fail("NODE_NOT_READY", f"Node {args.node} is {runtime['status']}, not READY")
		if sum(1 for item in state["nodes"].values() if item["status"] == "RUNNING") >= graph["max_parallel"]:
			fail("PARALLEL_LIMIT", f"Graph max_parallel={graph['max_parallel']} is already in use")
		input_artifacts = [*node["inputs"], *(artifact for artifact in node["optional_inputs"] if artifact in state["artifacts"])]
		for artifact in input_artifacts:
			record = state["artifacts"].get(artifact)
			if not record:
				fail("INPUT_MISSING", f"Node {args.node} lacks required artifact {artifact}")
			verify_artifact(project, artifact, record)
		workspace_revision = args.workspace_revision or git_text(project, ["rev-parse", "HEAD"])
		verify_commit(project, workspace_revision, "workspace_revision")
		require_ancestor(project, graph["base_revision"], workspace_revision)
		if node["kind"] != "merge":
			for artifact in input_artifacts:
				require_ancestor(project, state["artifacts"][artifact]["source_revision"], workspace_revision)
		token = f"tok_{secrets.token_hex(32)}"
		claim_id = f"CLM-{secrets.token_hex(8)}"
		runtime["status"] = "RUNNING"
		runtime["attempts"] += 1
		runtime["claim_id"] = claim_id
		runtime["claim_digest"] = digest_bytes(token.encode("utf-8"))
		runtime["worker"] = worker
		runtime["claim_revision"] = workspace_revision
		runtime["claimed_at"] = utc_now()
		runtime["updated_at"] = utc_now()
		runtime["last_event"] = append_event(
			state, "claim", node_id=args.node, activation=runtime["activation"],
			attempt=runtime["attempts"], claim_id=claim_id, claim_digest=runtime["claim_digest"],
			source_revision=workspace_revision,
		)
		persist_state(state_path, state, graph, digest, raw)
		result = state_summary(state, graph, state_path)
		result.update({"result": "NODE_CLAIMED", "node": args.node, "claim_id": claim_id, "claim_token": token, "workspace_revision": workspace_revision})
		return result


def output_contract(graph: dict[str, Any], node: dict[str, Any], outcome: str) -> tuple[set[str], set[str]]:
	status = OUTCOME_STATUS[outcome]
	matched = {
		artifact
		for edge in graph["edges"]
		if edge["from"] == node["id"] and edge["type"] in {"data", "loop"} and condition_matches(edge["condition"], status)
		for artifact in edge["consumes"]
	}
	if matched:
		return matched, matched
	has_data_output_edge = any(edge["from"] == node["id"] and edge["type"] in {"data", "loop"} for edge in graph["edges"])
	fallback = set(node["outputs"]) if outcome in {"success", "approve"} and not has_data_output_edge else set()
	return fallback, fallback


def clear_claim(runtime: dict[str, Any]) -> None:
	for field in ("claim_id", "claim_digest", "worker", "claim_revision", "claimed_at"):
		runtime[field] = ""


def finish_request_digest(outcome: str, retry: bool, note: str, artifacts: dict[str, dict[str, Any]], source_revision: str) -> str:
	payload = {
		"outcome": outcome,
		"retry": retry,
		"note": note,
		"artifacts": {name: {"path": record["path"], "digest": record["digest"], "bytes": record["bytes"]} for name, record in sorted(artifacts.items())},
		"source_revision": source_revision,
	}
	return digest_bytes(canonical_json(payload))


def finish_runtime(args: argparse.Namespace) -> dict[str, Any]:
	project, graph, digest, state_path = load_context(args)
	note = normalized_note(args.note, "note")
	claim_token = claim_token_value(args.claim_token)
	claim_digest = digest_bytes(claim_token.encode("utf-8"))
	with target_file_lock(state_path):
		verify_project_binding(project, graph)
		state, raw = read_state(state_path, graph, digest)
		require_revision(state, args.expected_revision)
		nodes = node_map(graph)
		if args.node not in nodes:
			fail("NODE_UNKNOWN", f"Unknown graph node: {args.node}")
		node = nodes[args.node]
		runtime = state["nodes"][args.node]
		if node["kind"] == "human" and args.outcome not in {"approve", "reject", "blocked", "cancelled"}:
			fail("OUTCOME_INVALID", "Human nodes must finish as approve, reject, blocked, or cancelled")
		if node["kind"] != "human" and args.outcome in {"approve", "reject"}:
			fail("OUTCOME_INVALID", "Only human nodes may approve or reject")
		if args.retry and args.outcome != "failure":
			fail("RETRY_INVALID", "--retry is allowed only with failure")
		if args.retry and args.artifact:
			fail("RETRY_ARTIFACT_INVALID", "Retryable failures cannot publish output artifacts")
		if runtime["status"] != "RUNNING":
			fail("NODE_NOT_RUNNING", f"Node {args.node} is {runtime['status']}, not RUNNING")
		if runtime["claim_digest"] != claim_digest:
			fail("CLAIM_MISMATCH", "Claim token does not own the current node lease")
		if state["transition_count"] >= graph["max_transitions"]:
			fail("TRANSITION_LIMIT", "Graph transition budget is exhausted")
		if args.retry and runtime["attempts"] >= node["max_attempts"]:
			fail("ATTEMPT_LIMIT", f"Node {args.node} has exhausted max_attempts={node['max_attempts']}")
		supplied = parse_artifact_specs(project, args.artifact)
		unknown = set(supplied) - set(node["outputs"])
		if unknown:
			fail("OUTPUT_UNKNOWN", f"Node {args.node} does not declare outputs {sorted(unknown)}")
		required, allowed = output_contract(graph, node, args.outcome)
		disallowed = set(supplied) - allowed
		if disallowed:
			fail("OUTPUT_NOT_ALLOWED", f"Outcome {args.outcome} cannot publish artifacts {sorted(disallowed)}")
		missing = required - set(supplied)
		if missing:
			fail("OUTPUT_MISSING", f"Outcome {args.outcome} requires artifacts {sorted(missing)}")
		source_revision = args.source_revision or git_text(project, ["rev-parse", "HEAD"])
		verify_commit(project, source_revision, "source_revision")
		require_ancestor(project, runtime["claim_revision"], source_revision)
		if node["write_scope"] and args.outcome == "success":
			if not args.source_revision:
				fail("SOURCE_REVISION_REQUIRED", "Successful writing nodes require an explicit --source-revision")
			verify_changed_scope(project, runtime["claim_revision"], source_revision, node["write_scope"])
		if node["kind"] == "merge" and args.outcome == "success":
			for artifact in node["inputs"]:
				require_ancestor(project, state["artifacts"][artifact]["source_revision"], source_revision)
		artifact_records = {
			name: artifact_record(name, relative, data, args.node, runtime["activation"], source_revision)
			for name, (relative, data) in supplied.items()
		}
		request_digest = finish_request_digest(args.outcome, args.retry, note, artifact_records, source_revision)
		for name, record in artifact_records.items():
			state["artifacts"][name] = record
		claim_id = runtime["claim_id"]
		activation = runtime["activation"]
		attempt = runtime["attempts"]
		if args.retry:
			runtime["status"] = "READY"
			runtime["last_outcome"] = "failure-retryable"
		else:
			runtime["status"] = OUTCOME_STATUS[args.outcome]
			runtime["last_outcome"] = args.outcome
		clear_claim(runtime)
		runtime["updated_at"] = utc_now()
		state["transition_count"] += 1
		runtime["last_event"] = append_event(
			state, "finish", node_id=args.node, activation=activation, attempt=attempt,
			claim_id=claim_id, claim_digest=claim_digest, outcome="failure-retryable" if args.retry else args.outcome,
			note=note, artifacts={name: record["digest"] for name, record in artifact_records.items()},
			source_revision=source_revision, request_digest=request_digest,
		)
		if not args.retry:
			activate_loops(state, graph, args.node)
		refresh_nonloop_nodes(state, graph)
		persist_state(state_path, state, graph, digest, raw)
		result = state_summary(state, graph, state_path)
		result.update({"result": "NODE_RECORDED", "node": args.node, "outcome": runtime["last_outcome"], "receipt_event": runtime["last_event"], "request_digest": request_digest})
		return result


def recover_runtime(args: argparse.Namespace) -> dict[str, Any]:
	project, graph, digest, state_path = load_context(args)
	note = normalized_note(args.note, "note")
	if not note:
		fail("NOTE_REQUIRED", "Recovery requires a non-empty reason")
	with target_file_lock(state_path):
		verify_project_binding(project, graph)
		state, raw = read_state(state_path, graph, digest)
		require_revision(state, args.expected_revision)
		nodes = node_map(graph)
		if args.node not in nodes:
			fail("NODE_UNKNOWN", f"Unknown graph node: {args.node}")
		node = nodes[args.node]
		runtime = state["nodes"][args.node]
		if runtime["status"] != "RUNNING" or runtime["claim_id"] != args.claim_id:
			fail("CLAIM_MISMATCH", "Recovery claim ID does not match the current running node")
		age = int((datetime.now(timezone.utc) - parse_time(runtime["claimed_at"])).total_seconds())
		if age < node["timeout_seconds"]:
			fail("CLAIM_NOT_STALE", f"Claim age {max(0, age)}s is below node timeout {node['timeout_seconds']}s")
		if state["transition_count"] >= graph["max_transitions"]:
			fail("TRANSITION_LIMIT", "Graph transition budget is exhausted")
		if args.action == "ready" and runtime["attempts"] >= node["max_attempts"]:
			fail("ATTEMPT_LIMIT", "Cannot requeue a stale claim after max_attempts")
		activation = runtime["activation"]
		attempt = runtime["attempts"]
		claim_id = runtime["claim_id"]
		claim_digest = runtime["claim_digest"]
		runtime["status"] = {"ready": "READY", "failed": "FAILED", "blocked": "BLOCKED"}[args.action]
		runtime["last_outcome"] = f"stale-{args.action}"
		clear_claim(runtime)
		runtime["updated_at"] = utc_now()
		state["transition_count"] += 1
		runtime["last_event"] = append_event(
			state, "recover", node_id=args.node, activation=activation, attempt=attempt,
			claim_id=claim_id, claim_digest=claim_digest, outcome=f"stale-{args.action}", note=note,
		)
		if args.action != "ready":
			activate_loops(state, graph, args.node)
		refresh_nonloop_nodes(state, graph)
		persist_state(state_path, state, graph, digest, raw)
		result = state_summary(state, graph, state_path)
		result.update({"result": "STALE_CLAIM_RECOVERED", "node": args.node, "action": args.action, "age_seconds": age})
		return result


def main() -> int:
	configure_utf8_stdio()
	args = parse_args()
	try:
		if args.command == "start":
			result = start_runtime(args)
		elif args.command == "status":
			result = status_runtime(args)
		elif args.command == "resume":
			result = status_runtime(args, resume=True)
		elif args.command == "claim":
			result = claim_runtime(args)
		elif args.command == "finish":
			result = finish_runtime(args)
		else:
			result = recover_runtime(args)
		print(json.dumps(result, ensure_ascii=False, indent=2))
		return 0
	except GraphRuntimeError as exc:
		print(json.dumps({"ok": False, "code": exc.code, "error": str(exc)}, ensure_ascii=False, indent=2))
		return 1
	except MemoryErrorWithCode as exc:
		print(json.dumps({"ok": False, "code": exc.code, "error": str(exc)}, ensure_ascii=False, indent=2))
		return 1
	except (OSError, ValueError, TypeError) as exc:
		print(json.dumps({"ok": False, "code": "IO_ERROR", "error": str(exc)}, ensure_ascii=False, indent=2))
		return 1


if __name__ == "__main__":
	raise SystemExit(main())
