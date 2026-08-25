#!/usr/bin/env python3
"""Durable, provider-neutral supervisor ledger for bounded Harness loops.

This runtime records triggers, iteration leases, verifier receipts, usage, and
stop decisions. It does not launch agents, execute verifier commands, schedule
work, modify source files, or authorize consequential actions.
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
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

sys.dont_write_bytecode = True

from bounded_json import unique_object
from memory_ops import (
	MemoryErrorWithCode,
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
from validate_loop_contract import load_contract, validate_contract


STATE_SCHEMA = 1
MAX_STATE_BYTES = 4 * 1024 * 1024
MAX_EVIDENCE_BYTES = 64 * 1024 * 1024
MAX_GIT_OUTPUT_BYTES = 2 * 1024 * 1024
MAX_EVENTS = 4096
MAX_NOTE_BYTES = 512
COMMIT_PATTERN = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
DELIVERY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
CLAIM_ID_PATTERN = re.compile(r"^LCL-[0-9a-f]{16}$")
CLAIM_TOKEN_PATTERN = re.compile(r"^ltok_[0-9a-f]{64}$")
DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
ACTIVE_STATUSES = {"ACTIVE", "PAUSED"}
TERMINAL_STATUSES = {
	"PASS_WITH_EVIDENCE", "CONDITIONAL", "BLOCKED", "BUDGET_EXHAUSTED",
	"NO_PROGRESS", "CANCELLED",
}
STATUSES = ACTIVE_STATUSES | TERMINAL_STATUSES | {"WAITING_TRIGGER"}
FINISH_OUTCOMES = {"pass", "improved", "no-progress", "failure", "blocked", "conditional"}
STATE_FIELDS = {
	"schema_version", "contract_digest", "loop_id", "project_id", "run_id",
	"source_revision", "revision", "status", "run_count", "completed_runs",
	"iteration", "total_iterations", "usage", "consecutive_failures",
	"no_progress_cycles", "active_claim", "queued_trigger_digest",
	"delivery_digests", "best_digest", "best_evidence_path", "best_source_revision", "last_outcome",
	"events", "created_at", "updated_at",
}
USAGE_FIELDS = {"tokens", "cost_microusd", "external_calls"}
CLAIM_FIELDS = {"claim_id", "claim_digest", "worker", "run_number", "iteration", "source_revision", "claimed_at"}
EVENT_FIELDS = {
	"sequence", "type", "run_number", "iteration", "claim_id", "claim_digest",
	"delivery_digest", "source_revision", "best_digest", "outcome", "note", "verifiers",
	"usage_delta", "at", "prev_digest", "event_digest",
}
EVENT_TYPES = {
	"start", "trigger", "trigger-skip", "trigger-queue", "claim", "finish",
	"queue-drop", "budget-stop", "pause", "resume", "cancel", "recover",
}


class LoopRuntimeError(RuntimeError):
	def __init__(self, code: str, message: str):
		super().__init__(message)
		self.code = code


def fail(code: str, message: str) -> None:
	raise LoopRuntimeError(code, message)


def canonical_json(data: Any) -> bytes:
	return (json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def digest_bytes(data: bytes) -> str:
	return f"sha256:{hashlib.sha256(data).hexdigest()}"


def contract_digest(contract: dict[str, Any]) -> str:
	return digest_bytes(canonical_json(contract))


def is_nonnegative_int(value: Any) -> bool:
	return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def valid_timestamp(value: Any) -> bool:
	if not isinstance(value, str):
		return False
	try:
		return parse_time(value) <= datetime.now(timezone.utc)
	except MemoryErrorWithCode:
		return False


def normalized_note(value: str, field: str) -> str:
	if not isinstance(value, str):
		fail("INVALID_FIELD", f"{field} must be a string")
	normalized = " ".join(value.strip().split())
	if len(normalized.encode("utf-8")) > MAX_NOTE_BYTES:
		fail("FIELD_TOO_LARGE", f"{field} exceeds {MAX_NOTE_BYTES} UTF-8 bytes")
	unsafe = unsafe_reason(normalized) if normalized else None
	if unsafe:
		fail("UNSAFE_RECEIPT", f"{field} contains {unsafe}; keep untrusted detail in a bounded evidence file")
	return normalized


def add_context_arguments(parser: argparse.ArgumentParser) -> None:
	parser.add_argument("--project", required=True, help="Harness project root")
	parser.add_argument("--contract", required=True, help="Active LOOP-CONTRACT.json")
	parser.add_argument("--state", help="Optional state file under .harness/.cache")


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Record and supervise bounded Harness loop execution")
	subparsers = parser.add_subparsers(dest="command", required=True)

	start = subparsers.add_parser("start", help="Bind a validated loop contract to the active project run")
	add_context_arguments(start)
	start.add_argument("--delivery-id", default="", help="Required unique delivery ID for scheduled/event starts")

	status = subparsers.add_parser("status", help="Read current supervisor state without mutation")
	add_context_arguments(status)
	status.add_argument("--verify-evidence", action="store_true", help="Re-hash best and current verifier evidence")

	trigger = subparsers.add_parser("trigger", help="Deliver one deduplicated scheduled/event trigger")
	add_context_arguments(trigger)
	trigger.add_argument("--delivery-id", required=True)
	trigger.add_argument("--expected-revision", required=True, type=int)

	claim = subparsers.add_parser("claim", help="Lease the next iteration to one backend worker")
	add_context_arguments(claim)
	claim.add_argument("--worker", required=True)
	claim.add_argument("--source-revision", help="Exact worker baseline; defaults to current HEAD")
	claim.add_argument("--expected-revision", required=True, type=int)

	finish = subparsers.add_parser("finish", help="Record one iteration outcome, evidence, and usage")
	add_context_arguments(finish)
	finish.add_argument("--claim-token", help="Lease token; prefer HARNESS_LOOP_CLAIM_TOKEN")
	finish.add_argument("--outcome", required=True, choices=sorted(FINISH_OUTCOMES))
	finish.add_argument("--result-revision", help="Exact accepted result commit for a writing iteration")
	finish.add_argument("--verifier", action="append", default=[], help="Verifier ID whose declared evidence file is complete")
	finish.add_argument("--accept-best", action="store_true", help="Digest the contract's declared best artifact")
	finish.add_argument("--tokens", type=int, default=0)
	finish.add_argument("--cost-microusd", type=int, default=0)
	finish.add_argument("--external-calls", type=int, default=0)
	finish.add_argument("--note", default="")
	finish.add_argument("--expected-revision", required=True, type=int)

	pause = subparsers.add_parser("pause", help="Stop new iteration claims without invalidating an active lease")
	add_context_arguments(pause)
	pause.add_argument("--note", required=True)
	pause.add_argument("--expected-revision", required=True, type=int)

	resume = subparsers.add_parser("resume", help="Resume a paused loop after re-verifying its bindings")
	add_context_arguments(resume)
	resume.add_argument("--expected-revision", required=True, type=int)

	cancel = subparsers.add_parser("cancel", help="Invalidate the active lease and stop the loop")
	add_context_arguments(cancel)
	cancel.add_argument("--note", required=True)
	cancel.add_argument("--expected-revision", required=True, type=int)

	recover = subparsers.add_parser("recover", help="Resolve an iteration lease after its declared timeout")
	add_context_arguments(recover)
	recover.add_argument("--claim-id", required=True)
	recover.add_argument("--action", required=True, choices=("continue", "blocked", "cancelled"))
	recover.add_argument("--note", required=True)
	recover.add_argument("--expected-revision", required=True, type=int)
	return parser.parse_args()


def run_git(project: Path, arguments: list[str], *, allow_failure: bool = False) -> tuple[int, bytes, bytes]:
	with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
		try:
			result = subprocess.run(
				["git", "-C", str(project), *arguments], stdout=stdout_file,
				stderr=stderr_file, timeout=20, check=False,
			)
		except (OSError, subprocess.TimeoutExpired) as exc:
			fail("GIT_UNAVAILABLE", f"Git command failed to start or timed out: {exc}")
		if stdout_file.tell() > MAX_GIT_OUTPUT_BYTES or stderr_file.tell() > MAX_GIT_OUTPUT_BYTES:
			fail("GIT_OUTPUT_TOO_LARGE", f"Git output exceeded {MAX_GIT_OUTPUT_BYTES} bytes")
		stdout_file.seek(0)
		stderr_file.seek(0)
		stdout = stdout_file.read()
		stderr = stderr_file.read()
	if result.returncode != 0 and not allow_failure:
		detail = stderr.decode("utf-8", errors="replace").strip()[:1000]
		fail("GIT_FAILED", detail or f"Git exited {result.returncode}")
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
		fail("INVALID_REVISION", f"{field} must be an exact lowercase commit ID")
	resolved = git_text(project, ["rev-parse", "--verify", f"{revision}^{{commit}}"])
	if resolved != revision:
		fail("REVISION_MISMATCH", f"{field} resolved to {resolved}, not the exact recorded commit")
	return resolved


def require_ancestor(project: Path, ancestor: str, descendant: str) -> None:
	code, _, _ = run_git(project, ["merge-base", "--is-ancestor", ancestor, descendant], allow_failure=True)
	if code != 0:
		fail("REVISION_DIVERGED", f"{descendant} is not descended from loop baseline {ancestor}")


def git_paths(project: Path, arguments: list[str]) -> list[str]:
	_, stdout, _ = run_git(project, arguments)
	try:
		return [item.decode("utf-8") for item in stdout.split(b"\0") if item]
	except UnicodeDecodeError as exc:
		fail("GIT_NON_UTF8", "Git path output is not UTF-8")
		raise AssertionError from exc


def outside_harness(paths: list[str]) -> list[str]:
	return sorted(path for path in paths if path != ".harness" and not path.startswith(".harness/"))


def path_in_scopes(path: str, scopes: list[str]) -> bool:
	path_parts = PurePosixPath(path).parts
	return any(
		scope == "." or path_parts[:len(PurePosixPath(scope).parts)] == PurePosixPath(scope).parts
		for scope in scopes
	)


def verify_changed_scope(project: Path, before: str, after: str, scopes: list[str]) -> list[str]:
	require_ancestor(project, before, after)
	paths = git_paths(project, ["diff", "--name-only", "-z", "--relative", before, after, "--", "."])
	violations = sorted(path for path in paths if not path_in_scopes(path, scopes))
	if violations:
		fail("WRITE_SCOPE_VIOLATION", f"Result commit changes paths outside control.write_scope: {violations[:20]}")
	return sorted(paths)


def verify_clean_source(project: Path, baseline: str) -> None:
	tracked = git_paths(project, ["diff", "--name-only", "-z", "--relative", baseline, "--", "."])
	untracked = git_paths(project, ["ls-files", "--others", "--exclude-standard", "-z", "--", "."])
	dirty = outside_harness([*tracked, *untracked])
	if dirty:
		fail("DIRTY_BASELINE", f"Iteration requires no source changes outside .harness; found {dirty[:10]}")


def resolve_project(value: str) -> Path:
	try:
		project = Path(value).expanduser().resolve(strict=True)
	except OSError as exc:
		fail("PROJECT_UNAVAILABLE", f"Cannot resolve project: {exc}")
	if not project.is_dir() or path_is_link_or_junction(project):
		fail("PROJECT_INVALID", f"Project must be a real directory: {project}")
	return project


def reject_linked_parents(path: Path, root: Path, label: str) -> None:
	root_path = Path(os.path.abspath(root))
	current = Path(os.path.abspath(path)).parent
	while current != root_path:
		if current == current.parent:
			fail("PATH_ESCAPE", f"{label} parent escapes its trusted root")
		if current.exists() and path_is_link_or_junction(current):
			fail("PATH_LINKED", f"{label} parent is linked: {current}")
		current = current.parent


def verify_project_binding(project: Path, contract: dict[str, Any]) -> None:
	harness = project / ".harness"
	if not harness.is_dir() or path_is_link_or_junction(harness):
		fail("HARNESS_ROOT_INVALID", f".harness must be a real project directory: {harness}")
	identity, _ = read_json_bytes(harness / "IDENTITY.json")
	errors = validate_identity(identity)
	if errors:
		fail("IDENTITY_INVALID", "; ".join(errors))
	assert_current_identity(project, identity, str(identity["logical_scope"]))
	if identity["project_id"] != contract["project_id"]:
		fail("PROJECT_MISMATCH", "Loop Project ID does not match .harness/IDENTITY.json")
	run_state, _ = read_json_bytes(harness / "STATE.json")
	if run_state.get("project_id") != contract["project_id"] or run_state.get("run_id") != contract["run_id"]:
		fail("RUN_MISMATCH", "Loop Project ID/Run ID do not match active .harness/STATE.json")
	if run_state.get("operation") not in {"start", "resume"}:
		fail("RUN_INACTIVE", "Loop runtime requires STATE.json operation start or resume")


def resolve_contract(project: Path, value: str) -> tuple[dict[str, Any], str]:
	path = Path(value).expanduser()
	if not path.is_absolute():
		path = project / path
	path = path.absolute()
	ensure_within(path, project, "loop contract")
	reject_linked_parents(path, project, "loop contract")
	data, errors = load_contract(path)
	if not errors:
		errors = validate_contract(data)
	if errors:
		fail("CONTRACT_INVALID", "; ".join(errors))
	if not data.get("project_id") or not data.get("run_id"):
		fail("CONTRACT_INACTIVE", "Runtime requires an active contract with Project ID and Run ID")
	verify_project_binding(project, data)
	return data, contract_digest(data)


def default_state_path(project: Path, contract: dict[str, Any]) -> Path:
	key = digest_bytes(f"{contract['project_id']}\0{contract['run_id']}\0{contract['loop_id']}".encode("utf-8"))[7:23]
	return project / ".harness" / ".cache" / "loop-runs" / f"{contract['loop_id']}-{key}.json"


def resolve_state_path(project: Path, contract: dict[str, Any], supplied: str | None) -> Path:
	cache_root = project / ".harness" / ".cache"
	cache_root.mkdir(parents=True, exist_ok=True)
	if path_is_link_or_junction(cache_root):
		fail("STATE_ROOT_LINKED", f"Loop state root cannot be linked: {cache_root}")
	path = default_state_path(project, contract) if not supplied else Path(supplied).expanduser()
	if not path.is_absolute():
		path = project / path
	path = path.absolute()
	ensure_within(path, cache_root, "loop runtime state")
	reject_linked_parents(path, cache_root, "loop runtime state")
	if path_is_link_or_junction(path):
		fail("STATE_LINKED", f"Loop state cannot be linked: {path}")
	return path


def load_context(args: argparse.Namespace) -> tuple[Path, dict[str, Any], str, Path]:
	project = resolve_project(args.project)
	contract, digest = resolve_contract(project, args.contract)
	return project, contract, digest, resolve_state_path(project, contract, args.state)


def source_baseline(project: Path, contract: dict[str, Any]) -> str:
	head = verify_commit(project, git_text(project, ["rev-parse", "HEAD"]), "HEAD")
	rollback = contract["control"]["rollback_revision"]
	if rollback:
		verify_commit(project, rollback, "control.rollback_revision")
		if head != rollback:
			fail("ROLLBACK_NOT_HEAD", f"Writing loop rollback revision {rollback} does not equal current HEAD {head}")
	baseline = rollback or head
	verify_clean_source(project, baseline)
	return baseline


def delivery_digest(contract: dict[str, Any], delivery_id: str) -> str:
	if not DELIVERY_PATTERN.fullmatch(delivery_id):
		fail("DELIVERY_ID_INVALID", "delivery-id must use 1 to 256 safe identifier characters")
	return digest_bytes(f"{contract['trigger']['dedupe_key']}\0{delivery_id}".encode("utf-8"))


def safe_evidence_path(project: Path, relative: str) -> Path:
	path_value = PurePosixPath(relative)
	if "\\" in relative or path_value.is_absolute() or ".." in path_value.parts:
		fail("EVIDENCE_PATH_INVALID", f"Evidence path is unsafe: {relative!r}")
	path = (project / path_value).absolute()
	ensure_within(path, project / ".harness", "loop evidence")
	reject_linked_parents(path, project / ".harness", "loop evidence")
	return path


def evidence_digest(project: Path, relative: str, label: str) -> str:
	path = safe_evidence_path(project, relative)
	try:
		raw = read_regular_file_bounded(path, MAX_EVIDENCE_BYTES, label)
	except (OSError, MemoryErrorWithCode) as exc:
		fail("EVIDENCE_UNAVAILABLE", f"Cannot read {label}: {exc}")
	return digest_bytes(raw)


def append_event(
	state: dict[str, Any], event_type: str, *, claim_id: str = "", claim_digest: str = "",
	delivery_digest: str = "", source_revision: str = "", best_digest: str = "",
	outcome: str = "", note: str = "", verifiers: dict[str, str] | None = None,
	usage_delta: dict[str, int] | None = None,
) -> int:
	if len(state["events"]) >= MAX_EVENTS:
		fail("EVENT_LIMIT", f"Loop event ledger reached {MAX_EVENTS} entries")
	event = {
		"sequence": len(state["events"]),
		"type": event_type,
		"run_number": state["run_count"],
		"iteration": state["iteration"],
		"claim_id": claim_id,
		"claim_digest": claim_digest,
		"delivery_digest": delivery_digest,
		"source_revision": source_revision,
		"best_digest": best_digest,
		"outcome": outcome,
		"note": note,
		"verifiers": verifiers or {},
		"usage_delta": usage_delta or {field: 0 for field in sorted(USAGE_FIELDS)},
		"at": utc_now(),
		"prev_digest": state["events"][-1]["event_digest"] if state["events"] else "",
		"event_digest": "",
	}
	event["event_digest"] = digest_bytes(canonical_json({key: value for key, value in event.items() if key != "event_digest"}))
	state["events"].append(event)
	return event["sequence"]


def new_state(contract: dict[str, Any], digest: str, source_revision: str, initial_delivery: str) -> dict[str, Any]:
	now = utc_now()
	state = {
		"schema_version": STATE_SCHEMA,
		"contract_digest": digest,
		"loop_id": contract["loop_id"],
		"project_id": contract["project_id"],
		"run_id": contract["run_id"],
		"source_revision": source_revision,
		"revision": 0,
		"status": "ACTIVE",
		"run_count": 1,
		"completed_runs": 0,
		"iteration": 0,
		"total_iterations": 0,
		"usage": {field: 0 for field in sorted(USAGE_FIELDS)},
		"consecutive_failures": 0,
		"no_progress_cycles": 0,
		"active_claim": None,
		"queued_trigger_digest": "",
		"delivery_digests": [initial_delivery] if initial_delivery else [],
		"best_digest": "",
		"best_evidence_path": "",
		"best_source_revision": "",
		"last_outcome": "",
		"events": [],
		"created_at": now,
		"updated_at": now,
	}
	append_event(
		state, "start", delivery_digest=initial_delivery, source_revision=source_revision,
		note="Bounded loop runtime started",
	)
	return state


def validate_event_chain(events: Any, contract: dict[str, Any]) -> list[str]:
	errors: list[str] = []
	verifier_ids = {verifier["id"] for verifier in contract["verifiers"]}
	valid_outcomes = FINISH_OUTCOMES | {"", "cancelled", "stale-continue", "stale-blocked", "stale-cancelled"}
	if not isinstance(events, list) or not 1 <= len(events) <= MAX_EVENTS:
		return ["events must be a bounded non-empty array"]
	previous = ""
	for sequence, event in enumerate(events):
		if not isinstance(event, dict) or set(event) != EVENT_FIELDS:
			errors.append(f"event {sequence} has invalid fields")
			break
		if event.get("sequence") != sequence or event.get("prev_digest") != previous:
			errors.append(f"event {sequence} breaks the event chain")
			break
		expected = digest_bytes(canonical_json({key: value for key, value in event.items() if key != "event_digest"}))
		if event.get("event_digest") != expected:
			errors.append(f"event {sequence} digest mismatch")
			break
		if not isinstance(event.get("type"), str) or event["type"] not in EVENT_TYPES or not valid_timestamp(event.get("at")):
			errors.append(f"event {sequence} has invalid type or timestamp")
		if not is_nonnegative_int(event.get("run_number")) or not is_nonnegative_int(event.get("iteration")):
			errors.append(f"event {sequence} has invalid counters")
		elif not 1 <= event["run_number"] <= contract["trigger"]["max_runs"] or event["iteration"] > contract["budgets"]["max_iterations"]:
			errors.append(f"event {sequence} counters exceed the contract")
		if event.get("claim_id") and not CLAIM_ID_PATTERN.fullmatch(str(event["claim_id"])):
			errors.append(f"event {sequence} has invalid claim ID")
		if event.get("claim_digest") and not DIGEST_PATTERN.fullmatch(str(event["claim_digest"])):
			errors.append(f"event {sequence} has invalid claim digest")
		if event.get("delivery_digest") and not DIGEST_PATTERN.fullmatch(str(event["delivery_digest"])):
			errors.append(f"event {sequence} has invalid delivery digest")
		if event.get("source_revision") and not COMMIT_PATTERN.fullmatch(str(event["source_revision"])):
			errors.append(f"event {sequence} has invalid source revision")
		if event.get("best_digest") and not DIGEST_PATTERN.fullmatch(str(event["best_digest"])):
			errors.append(f"event {sequence} has invalid best digest")
		if not isinstance(event.get("outcome"), str) or event["outcome"] not in valid_outcomes:
			errors.append(f"event {sequence} has invalid outcome")
		note = event.get("note")
		if not isinstance(note, str) or len(note.encode("utf-8")) > MAX_NOTE_BYTES or (note and unsafe_reason(note)):
			errors.append(f"event {sequence} has invalid note")
		if not isinstance(event.get("verifiers"), dict) or not set(event["verifiers"]).issubset(verifier_ids) or any(not DIGEST_PATTERN.fullmatch(str(value)) for value in event["verifiers"].values()):
			errors.append(f"event {sequence} has invalid verifier receipts")
		if not isinstance(event.get("usage_delta"), dict) or set(event["usage_delta"]) != USAGE_FIELDS or any(not is_nonnegative_int(value) for value in event["usage_delta"].values()):
			errors.append(f"event {sequence} has invalid usage delta")
		previous = event["event_digest"]
	return errors


def validate_state(state: Any, contract: dict[str, Any], digest: str) -> list[str]:
	if not isinstance(state, dict):
		return ["loop runtime state root must be an object"]
	errors: list[str] = []
	if set(state) != STATE_FIELDS:
		errors.append("loop runtime state fields do not match schema")
		return errors
	if state["schema_version"] != STATE_SCHEMA or state["contract_digest"] != digest:
		errors.append("contract changed after runtime start")
	for field in ("loop_id", "project_id", "run_id"):
		if state[field] != contract[field]:
			errors.append(f"state {field} differs from contract")
	if not COMMIT_PATTERN.fullmatch(str(state["source_revision"])):
		errors.append("source_revision is invalid")
	if state["best_source_revision"] and not COMMIT_PATTERN.fullmatch(str(state["best_source_revision"])):
		errors.append("best_source_revision is invalid")
	if not isinstance(state["status"], str) or state["status"] not in STATUSES:
		errors.append("status is invalid")
	for field in ("revision", "completed_runs", "iteration", "total_iterations", "consecutive_failures", "no_progress_cycles"):
		if not is_nonnegative_int(state[field]):
			errors.append(f"{field} must be a non-negative integer")
	if not isinstance(state["run_count"], int) or isinstance(state["run_count"], bool) or not 1 <= state["run_count"] <= contract["trigger"]["max_runs"]:
		errors.append("run_count is outside the contract")
	if is_nonnegative_int(state["completed_runs"]) and state["completed_runs"] > state["run_count"]:
		errors.append("completed_runs exceeds run_count")
	if is_nonnegative_int(state["revision"]) and isinstance(state["events"], list) and state["revision"] > len(state["events"]) - 1:
		errors.append("revision exceeds recorded mutations")
	if is_nonnegative_int(state["iteration"]) and state["iteration"] > contract["budgets"]["max_iterations"]:
		errors.append("iteration exceeds the per-run budget")
	maximum_total = contract["trigger"]["max_runs"] * contract["budgets"]["max_iterations"]
	if is_nonnegative_int(state["total_iterations"]) and state["total_iterations"] > maximum_total:
		errors.append("total_iterations exceeds the contract")
	if is_nonnegative_int(state["total_iterations"]) and is_nonnegative_int(state["iteration"]) and state["total_iterations"] < state["iteration"]:
		errors.append("total_iterations is below the current run iteration")
	if not isinstance(state["usage"], dict) or set(state["usage"]) != USAGE_FIELDS or any(not is_nonnegative_int(value) for value in state["usage"].values()):
		errors.append("usage is invalid")
	claim = state["active_claim"]
	if claim is not None:
		if not isinstance(claim, dict) or set(claim) != CLAIM_FIELDS:
			errors.append("active_claim has invalid fields")
		elif not CLAIM_ID_PATTERN.fullmatch(str(claim["claim_id"])) or not DIGEST_PATTERN.fullmatch(str(claim["claim_digest"])) or not valid_timestamp(claim["claimed_at"]):
			errors.append("active_claim has invalid identity or timestamp")
		elif not isinstance(claim["worker"], str) or not claim["worker"] or len(claim["worker"].encode("utf-8")) > MAX_NOTE_BYTES or unsafe_reason(claim["worker"]):
			errors.append("active_claim worker is invalid")
		elif not COMMIT_PATTERN.fullmatch(str(claim["source_revision"])):
			errors.append("active_claim source_revision is invalid")
		elif claim["run_number"] != state["run_count"] or claim["iteration"] != state["iteration"]:
			errors.append("active_claim counters differ from state")
		elif state["status"] not in ACTIVE_STATUSES:
			errors.append("only active or paused state may retain a claim")
	deliveries = state["delivery_digests"]
	if not isinstance(deliveries, list) or len(deliveries) > contract["trigger"]["max_runs"] or any(not isinstance(value, str) or not DIGEST_PATTERN.fullmatch(value) for value in deliveries):
		errors.append("delivery_digests is invalid")
	elif len(deliveries) != len(set(deliveries)):
		errors.append("delivery_digests contains duplicates")
	for field in ("queued_trigger_digest", "best_digest"):
		if state[field] and not DIGEST_PATTERN.fullmatch(str(state[field])):
			errors.append(f"{field} is invalid")
	if state["best_evidence_path"] and state["best_evidence_path"] != contract["evidence"]["best_artifact_path"]:
		errors.append("best_evidence_path differs from contract")
	if bool(state["best_digest"]) != bool(state["best_evidence_path"]):
		errors.append("best digest and evidence path must be recorded together")
	if state["best_source_revision"] and not state["best_digest"]:
		errors.append("best_source_revision requires best evidence")
	if contract["control"]["write_scope"] and state["best_digest"] and not state["best_source_revision"]:
		errors.append("writing loop best evidence requires best_source_revision")
	events = state["events"] if isinstance(state["events"], list) else []
	if events:
		accepted_deliveries = [
			event["delivery_digest"] for event in events
			if isinstance(event, dict) and event.get("type") in {"start", "trigger", "trigger-skip"} and event.get("delivery_digest")
		]
		if isinstance(deliveries, list) and deliveries != accepted_deliveries:
			errors.append("delivery state differs from event receipts")
		queued = ""
		for event in events:
			if not isinstance(event, dict):
				continue
			if event.get("type") == "trigger-queue":
				queued = event.get("delivery_digest", "")
			elif event.get("type") in {"trigger", "queue-drop"} and event.get("delivery_digest") == queued:
				queued = ""
		if state["queued_trigger_digest"] != queued:
			errors.append("queued trigger differs from event receipts")
		expected_usage = {field: 0 for field in USAGE_FIELDS}
		for event in events:
			if isinstance(event, dict) and isinstance(event.get("usage_delta"), dict):
				for field in USAGE_FIELDS:
					value = event["usage_delta"].get(field)
					if is_nonnegative_int(value):
						expected_usage[field] += value
		if state["usage"] != expected_usage:
			errors.append("usage totals differ from event receipts")
		recorded_sources = [event.get("source_revision") for event in events if isinstance(event, dict) and event.get("source_revision")]
		if recorded_sources and state["source_revision"] != recorded_sources[-1]:
			errors.append("accepted source differs from event receipts")
		recorded_best = [event.get("best_digest") for event in events if isinstance(event, dict) and event.get("best_digest")]
		if state["best_digest"] != (recorded_best[-1] if recorded_best else ""):
			errors.append("best artifact differs from event receipts")
		best_events = [event for event in events if isinstance(event, dict) and event.get("best_digest")]
		if state["best_source_revision"] != (best_events[-1].get("source_revision", "") if best_events else ""):
			errors.append("best source differs from event receipts")
		started_runs = sum(1 for event in events if isinstance(event, dict) and event.get("type") in {"start", "trigger"})
		completed_runs = sum(1 for event in events if isinstance(event, dict) and event.get("type") == "finish" and event.get("outcome") == "pass")
		claim_events = [event for event in events if isinstance(event, dict) and event.get("type") == "claim"]
		if state["run_count"] != started_runs or state["completed_runs"] != completed_runs or state["total_iterations"] != len(claim_events):
			errors.append("run or iteration counters differ from event receipts")
		current_run_iteration = sum(1 for event in claim_events if event.get("run_number") == state["run_count"])
		if state["iteration"] != current_run_iteration:
			errors.append("current iteration counter differs from event receipts")
		active_receipt: tuple[str, str] | None = None
		for event in events:
			if not isinstance(event, dict):
				continue
			if event.get("type") == "claim":
				active_receipt = (event.get("claim_id", ""), event.get("claim_digest", ""))
			elif event.get("type") in {"finish", "recover", "cancel"} and active_receipt and event.get("claim_id") == active_receipt[0]:
				active_receipt = None
		active_state = None if not isinstance(claim, dict) else (claim.get("claim_id", ""), claim.get("claim_digest", ""))
		if active_state != active_receipt:
			errors.append("active claim differs from event receipts")
	active_or_waiting = isinstance(state["status"], str) and state["status"] in ACTIVE_STATUSES | {"WAITING_TRIGGER"}
	if active_or_waiting and is_nonnegative_int(state["consecutive_failures"]) and state["consecutive_failures"] >= contract["budgets"]["max_consecutive_failures"]:
		errors.append("non-terminal state exceeds the consecutive failure stop")
	if active_or_waiting and is_nonnegative_int(state["no_progress_cycles"]) and state["no_progress_cycles"] >= contract["budgets"]["no_progress_cycles"]:
		errors.append("non-terminal state exceeds the no-progress stop")
	if state["status"] == "WAITING_TRIGGER" and is_nonnegative_int(state["completed_runs"]) and isinstance(state["run_count"], int) and state["completed_runs"] != state["run_count"]:
		errors.append("waiting state requires the current run to be complete")
	if state["status"] == "PASS_WITH_EVIDENCE" and is_nonnegative_int(state["completed_runs"]) and isinstance(state["run_count"], int) and state["completed_runs"] != state["run_count"]:
		errors.append("passing state requires all started runs to be complete")
	errors.extend(validate_event_chain(state["events"], contract))
	if not valid_timestamp(state["created_at"]) or not valid_timestamp(state["updated_at"]):
		errors.append("state timestamps are invalid")
	return errors


def read_state(path: Path, contract: dict[str, Any], digest: str) -> tuple[dict[str, Any], bytes]:
	try:
		raw = read_regular_file_bounded(path, MAX_STATE_BYTES, "loop runtime state")
	except (OSError, MemoryErrorWithCode) as exc:
		fail("STATE_UNAVAILABLE", f"Cannot read loop runtime state: {exc}")
	try:
		state = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
	except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError, MemoryError) as exc:
		fail("STATE_INVALID", f"Loop runtime state is invalid JSON: {exc}")
	errors = validate_state(state, contract, digest)
	if errors:
		fail("STATE_INVALID", "; ".join(errors))
	return state, raw


def require_revision(state: dict[str, Any], expected: int) -> None:
	if expected != state["revision"]:
		fail("REVISION_CONFLICT", f"Expected state revision {expected}, current revision is {state['revision']}")


def persist_state(path: Path, state: dict[str, Any], contract: dict[str, Any], digest: str, expected: bytes) -> None:
	state["revision"] += 1
	state["updated_at"] = utc_now()
	errors = validate_state(state, contract, digest)
	if errors:
		fail("STATE_INVALID_AFTER_MUTATION", "; ".join(errors))
	atomic_replace(path, pretty_json(state), expected=expected)


def elapsed_seconds(state: dict[str, Any]) -> int:
	return max(0, int((datetime.now(timezone.utc) - parse_time(state["created_at"])).total_seconds()))


def exhausted_reason(state: dict[str, Any], contract: dict[str, Any], *, include_iterations: bool = True) -> str:
	budgets = contract["budgets"]
	if elapsed_seconds(state) >= budgets["max_elapsed_seconds"]:
		return "max_elapsed_seconds"
	if state["usage"]["tokens"] >= budgets["max_tokens"]:
		return "max_tokens"
	if (budgets["max_cost_microusd"] == 0 and state["usage"]["cost_microusd"] > 0) or (
		budgets["max_cost_microusd"] > 0 and state["usage"]["cost_microusd"] >= budgets["max_cost_microusd"]
	):
		return "max_cost_microusd"
	if (budgets["max_external_calls"] == 0 and state["usage"]["external_calls"] > 0) or (
		budgets["max_external_calls"] > 0 and state["usage"]["external_calls"] >= budgets["max_external_calls"]
	):
		return "max_external_calls"
	if include_iterations and state["iteration"] >= budgets["max_iterations"]:
		return "max_iterations"
	return ""


def verify_runtime_binding(project: Path, state: dict[str, Any]) -> None:
	verify_commit(project, state["source_revision"], "source_revision")
	head = verify_commit(project, git_text(project, ["rev-parse", "HEAD"]), "HEAD")
	require_ancestor(project, state["source_revision"], head)


def state_summary(state: dict[str, Any], contract: dict[str, Any], path: Path) -> dict[str, Any]:
	claim = state["active_claim"]
	remaining = {
		"iterations": max(0, contract["budgets"]["max_iterations"] - state["iteration"]),
		"elapsed_seconds": max(0, contract["budgets"]["max_elapsed_seconds"] - elapsed_seconds(state)),
		"tokens": max(0, contract["budgets"]["max_tokens"] - state["usage"]["tokens"]),
		"cost_microusd": max(0, contract["budgets"]["max_cost_microusd"] - state["usage"]["cost_microusd"]),
		"external_calls": max(0, contract["budgets"]["max_external_calls"] - state["usage"]["external_calls"]),
	}
	return {
		"ok": True,
		"result": "LOOP_STATE",
		"state_path": str(path),
		"loop_id": state["loop_id"],
		"project_id": state["project_id"],
		"run_id": state["run_id"],
		"source_revision": state["source_revision"],
		"revision": state["revision"],
		"status": state["status"],
		"run_count": state["run_count"],
		"completed_runs": state["completed_runs"],
		"iteration": state["iteration"],
		"total_iterations": state["total_iterations"],
		"usage": state["usage"],
		"remaining": remaining,
		"consecutive_failures": state["consecutive_failures"],
		"no_progress_cycles": state["no_progress_cycles"],
		"active_claim": None if claim is None else {
			"claim_id": claim["claim_id"], "worker": claim["worker"],
			"iteration": claim["iteration"],
			"age_seconds": max(0, int((datetime.now(timezone.utc) - parse_time(claim["claimed_at"])).total_seconds())),
			"timeout_seconds": contract["budgets"]["max_iteration_seconds"],
		},
		"queued_trigger": bool(state["queued_trigger_digest"]),
		"best_digest": state["best_digest"],
		"best_evidence_path": state["best_evidence_path"],
		"best_source_revision": state["best_source_revision"],
		"last_outcome": state["last_outcome"],
		"budget_stop_reason": exhausted_reason(
			state, contract,
			include_iterations=state["status"] != "WAITING_TRIGGER" and state["active_claim"] is None,
		),
	}


def start_runtime(args: argparse.Namespace) -> dict[str, Any]:
	project, contract, digest, state_path = load_context(args)
	trigger_type = contract["trigger"]["type"]
	if trigger_type == "human" and args.delivery_id:
		fail("DELIVERY_ID_UNEXPECTED", "Human-triggered loops do not accept a delivery ID")
	if trigger_type != "human" and not args.delivery_id:
		fail("DELIVERY_ID_REQUIRED", "Scheduled/event loops require a unique delivery ID")
	initial_delivery = delivery_digest(contract, args.delivery_id) if args.delivery_id else ""
	with target_file_lock(state_path):
		verify_project_binding(project, contract)
		baseline = source_baseline(project, contract)
		state = new_state(contract, digest, baseline, initial_delivery)
		errors = validate_state(state, contract, digest)
		if errors:
			fail("STATE_INVALID_AFTER_MUTATION", "; ".join(errors))
		atomic_replace(state_path, pretty_json(state), expected=None)
		result = state_summary(state, contract, state_path)
		result["result"] = "LOOP_STARTED"
		return result


def status_runtime(args: argparse.Namespace) -> dict[str, Any]:
	project, contract, digest, state_path = load_context(args)
	state, _ = read_state(state_path, contract, digest)
	verify_runtime_binding(project, state)
	if args.verify_evidence:
		if (
			state["best_evidence_path"]
			and evidence_digest(project, state["best_evidence_path"], "best loop artifact") != state["best_digest"]
		):
			fail("EVIDENCE_DRIFT", "Best loop artifact changed after receipt")
		latest_receipts: dict[str, str] = {}
		for event in state["events"]:
			latest_receipts.update(event["verifiers"])
		for verifier_id, expected in latest_receipts.items():
			verifier = next(item for item in contract["verifiers"] if item["id"] == verifier_id)
			if evidence_digest(project, verifier["evidence_path"], f"verifier {verifier_id}") != expected:
				fail("EVIDENCE_DRIFT", f"Current verifier evidence differs from its latest receipt: {verifier_id}")
	result = state_summary(state, contract, state_path)
	result["evidence_verified"] = bool(args.verify_evidence)
	return result


def begin_next_run(state: dict[str, Any]) -> None:
	state["run_count"] += 1
	state["iteration"] = 0
	state["consecutive_failures"] = 0
	state["no_progress_cycles"] = 0
	state["last_outcome"] = ""
	state["status"] = "ACTIVE"


def drop_queued_trigger(state: dict[str, Any], note: str) -> None:
	if not state["queued_trigger_digest"]:
		return
	delivery = state["queued_trigger_digest"]
	state["queued_trigger_digest"] = ""
	append_event(state, "queue-drop", delivery_digest=delivery, note=note)


def trigger_runtime(args: argparse.Namespace) -> dict[str, Any]:
	project, contract, digest, state_path = load_context(args)
	if contract["trigger"]["type"] == "human":
		fail("TRIGGER_INVALID", "Human-triggered loops cannot receive scheduled/event deliveries")
	delivery = delivery_digest(contract, args.delivery_id)
	with target_file_lock(state_path):
		state, raw = read_state(state_path, contract, digest)
		require_revision(state, args.expected_revision)
		verify_runtime_binding(project, state)
		if delivery in state["delivery_digests"] or delivery == state["queued_trigger_digest"]:
			fail("TRIGGER_DUPLICATE", "This delivery was already accepted or queued")
		accepted_deliveries = len(state["delivery_digests"]) + int(bool(state["queued_trigger_digest"]))
		if accepted_deliveries >= contract["trigger"]["max_runs"]:
			fail("DELIVERY_LIMIT", "trigger.max_runs delivery budget is exhausted")
		if state["run_count"] >= contract["trigger"]["max_runs"]:
			fail("RUN_LIMIT", "trigger.max_runs is exhausted")
		if state["status"] in ACTIVE_STATUSES:
			policy = contract["trigger"]["overlap_policy"]
			if policy == "reject":
				fail("TRIGGER_OVERLAP", "An active run already owns this contract")
			if policy == "skip":
				state["delivery_digests"].append(delivery)
				append_event(
					state, "trigger-skip", delivery_digest=delivery,
					note="Overlapping delivery skipped by contract policy",
				)
				persist_state(state_path, state, contract, digest, raw)
				result = state_summary(state, contract, state_path)
				result["result"] = "TRIGGER_SKIPPED"
				return result
			if state["queued_trigger_digest"]:
				fail("TRIGGER_QUEUE_FULL", "queue-one already contains a pending delivery")
			state["queued_trigger_digest"] = delivery
			append_event(state, "trigger-queue", delivery_digest=delivery, note="One overlapping delivery queued")
			persist_state(state_path, state, contract, digest, raw)
			result = state_summary(state, contract, state_path)
			result["result"] = "TRIGGER_QUEUED"
			return result
		if state["status"] != "WAITING_TRIGGER":
			fail("LOOP_TERMINAL", f"Loop is {state['status']}, not waiting for another trigger")
		reason = exhausted_reason(state, contract, include_iterations=False)
		if reason:
			state["status"] = "BUDGET_EXHAUSTED"
			state["last_outcome"] = reason
			append_event(
				state, "budget-stop", source_revision=state["source_revision"],
				note=f"Stopped before delivery: {reason}",
			)
			persist_state(state_path, state, contract, digest, raw)
			return state_summary(state, contract, state_path)
		state["delivery_digests"].append(delivery)
		begin_next_run(state)
		append_event(
			state, "trigger", delivery_digest=delivery,
			source_revision=state["source_revision"], note="Deduplicated delivery started the next run",
		)
		persist_state(state_path, state, contract, digest, raw)
		result = state_summary(state, contract, state_path)
		result["result"] = "TRIGGER_ACCEPTED"
		return result


def claim_token_value(supplied: str | None) -> str:
	environment = os.environ.get("HARNESS_LOOP_CLAIM_TOKEN", "")
	if supplied and environment and supplied != environment:
		fail("CLAIM_TOKEN_CONFLICT", "CLI and HARNESS_LOOP_CLAIM_TOKEN values differ")
	token = supplied or environment
	if not CLAIM_TOKEN_PATTERN.fullmatch(token):
		fail("CLAIM_TOKEN_INVALID", "Provide the exact lease token through HARNESS_LOOP_CLAIM_TOKEN or --claim-token")
	return token


def claim_runtime(args: argparse.Namespace) -> dict[str, Any]:
	project, contract, digest, state_path = load_context(args)
	worker = normalized_note(args.worker, "worker")
	if not worker:
		fail("WORKER_REQUIRED", "worker must not be empty")
	with target_file_lock(state_path):
		state, raw = read_state(state_path, contract, digest)
		require_revision(state, args.expected_revision)
		if state["status"] != "ACTIVE":
			fail("LOOP_NOT_ACTIVE", f"Loop is {state['status']}, not ACTIVE")
		if state["active_claim"] is not None:
			fail("ITERATION_RUNNING", "One iteration lease is already active")
		reason = exhausted_reason(state, contract)
		if reason:
			state["status"] = "BUDGET_EXHAUSTED"
			state["last_outcome"] = reason
			append_event(
				state, "budget-stop", source_revision=state["source_revision"],
				note=f"Stopped before iteration: {reason}",
			)
			persist_state(state_path, state, contract, digest, raw)
			result = state_summary(state, contract, state_path)
			result["result"] = "LOOP_STOPPED"
			return result
		source_revision = args.source_revision or git_text(project, ["rev-parse", "HEAD"])
		verify_commit(project, source_revision, "source_revision")
		if source_revision != state["source_revision"]:
			fail("SOURCE_NOT_ACCEPTED", f"Iteration must start from accepted source revision {state['source_revision']}")
		verify_runtime_binding(project, state)
		verify_clean_source(project, source_revision)
		token = f"ltok_{secrets.token_hex(32)}"
		claim_id = f"LCL-{secrets.token_hex(8)}"
		state["iteration"] += 1
		state["total_iterations"] += 1
		state["active_claim"] = {
			"claim_id": claim_id,
			"claim_digest": digest_bytes(token.encode("utf-8")),
			"worker": worker,
			"run_number": state["run_count"],
			"iteration": state["iteration"],
			"source_revision": source_revision,
			"claimed_at": utc_now(),
		}
		append_event(
			state, "claim", claim_id=claim_id, claim_digest=state["active_claim"]["claim_digest"],
			source_revision=source_revision,
		)
		persist_state(state_path, state, contract, digest, raw)
		result = state_summary(state, contract, state_path)
		result.update({
			"result": "ITERATION_CLAIMED", "claim_id": claim_id, "claim_token": token,
			"source_revision": source_revision,
			"verifier_ids": [verifier["id"] for verifier in contract["verifiers"]],
		})
		return result


def finish_runtime(args: argparse.Namespace) -> dict[str, Any]:
	project, contract, digest, state_path = load_context(args)
	note = normalized_note(args.note, "note")
	claim_token = claim_token_value(args.claim_token)
	claim_digest = digest_bytes(claim_token.encode("utf-8"))
	usage_delta = {"tokens": args.tokens, "cost_microusd": args.cost_microusd, "external_calls": args.external_calls}
	if any(not is_nonnegative_int(value) for value in usage_delta.values()):
		fail("USAGE_INVALID", "Usage deltas must be non-negative integers")
	if usage_delta["tokens"] > 1_000_000_000 or usage_delta["cost_microusd"] > 1_000_000_000_000 or usage_delta["external_calls"] > 10_000:
		fail("USAGE_INVALID", "Usage delta exceeds the maximum representable contract budget")
	requested_verifiers = args.verifier
	if len(requested_verifiers) != len(set(requested_verifiers)):
		fail("VERIFIER_DUPLICATE", "A verifier ID was supplied more than once")
	verifier_map = {verifier["id"]: verifier for verifier in contract["verifiers"]}
	unknown = set(requested_verifiers) - set(verifier_map)
	if unknown:
		fail("VERIFIER_UNKNOWN", f"Unknown verifier IDs: {sorted(unknown)}")
	if args.outcome == "pass" and set(requested_verifiers) != set(verifier_map):
		fail("VERIFIER_INCOMPLETE", "A passing iteration requires receipts for every declared verifier")
	if args.outcome == "pass" and not args.accept_best:
		fail("BEST_REQUIRED", "A passing iteration must record --accept-best evidence")
	if args.accept_best and args.outcome not in {"pass", "improved"}:
		fail("BEST_OUTCOME_INVALID", "Only pass or improved outcomes may accept a new best artifact")
	write_scopes = contract["control"]["write_scope"]
	if args.result_revision and args.outcome not in {"pass", "improved"}:
		fail("RESULT_REVISION_INVALID", "Only pass or improved outcomes may accept a result revision")
	if not write_scopes and args.result_revision:
		fail("RESULT_REVISION_UNEXPECTED", "A read-only loop cannot accept a result revision")
	with target_file_lock(state_path):
		state, raw = read_state(state_path, contract, digest)
		require_revision(state, args.expected_revision)
		claim = state["active_claim"]
		if state["status"] not in ACTIVE_STATUSES or claim is None:
			fail("ITERATION_NOT_RUNNING", "No active iteration lease can accept this result")
		if claim["claim_digest"] != claim_digest:
			fail("CLAIM_MISMATCH", "Claim token does not own the active iteration lease")
		result_revision = ""
		if write_scopes and args.outcome in {"pass", "improved"}:
			if not args.result_revision:
				fail("RESULT_REVISION_REQUIRED", "A passing or improved writing iteration requires --result-revision")
			result_revision = verify_commit(project, args.result_revision, "result_revision")
			verify_changed_scope(project, claim["source_revision"], result_revision, write_scopes)
		verifier_receipts = {
			verifier_id: evidence_digest(project, verifier_map[verifier_id]["evidence_path"], f"verifier {verifier_id}")
			for verifier_id in requested_verifiers
		}
		best_digest = evidence_digest(project, contract["evidence"]["best_artifact_path"], "best loop artifact") if args.accept_best else ""
		for field, delta in usage_delta.items():
			state["usage"][field] += delta
		state["active_claim"] = None
		state["last_outcome"] = args.outcome
		if args.accept_best:
			state["best_digest"] = best_digest
			state["best_evidence_path"] = contract["evidence"]["best_artifact_path"]
			state["best_source_revision"] = result_revision
		if result_revision:
			state["source_revision"] = result_revision
		if args.outcome in {"pass", "improved"}:
			state["consecutive_failures"] = 0
			state["no_progress_cycles"] = 0
		elif args.outcome == "failure":
			state["consecutive_failures"] += 1
		elif args.outcome == "no-progress":
			state["consecutive_failures"] = 0
			state["no_progress_cycles"] += 1
		append_event(
			state, "finish", claim_id=claim["claim_id"], claim_digest=claim_digest,
			source_revision=result_revision, best_digest=best_digest, outcome=args.outcome, note=note,
			verifiers=verifier_receipts, usage_delta=usage_delta,
		)
		if args.outcome == "pass":
			state["completed_runs"] += 1
			if contract["level"] in {"scheduled", "proactive"} and state["run_count"] < contract["trigger"]["max_runs"]:
				if state["queued_trigger_digest"]:
					queued_delivery = state["queued_trigger_digest"]
					state["delivery_digests"].append(queued_delivery)
					state["queued_trigger_digest"] = ""
					begin_next_run(state)
					append_event(
						state, "trigger", delivery_digest=queued_delivery,
						source_revision=state["source_revision"],
						note="Queued delivery started after the prior run completed",
					)
				else:
					state["status"] = "WAITING_TRIGGER"
			else:
				state["status"] = "PASS_WITH_EVIDENCE"
		elif args.outcome == "blocked":
			state["status"] = "BLOCKED"
		elif args.outcome == "conditional":
			state["status"] = "CONDITIONAL"
		elif state["consecutive_failures"] >= contract["budgets"]["max_consecutive_failures"]:
			state["status"] = "BLOCKED"
		elif state["no_progress_cycles"] >= contract["budgets"]["no_progress_cycles"]:
			state["status"] = "NO_PROGRESS"
		else:
			state["status"] = "PAUSED" if state["status"] == "PAUSED" else "ACTIVE"
		reason = exhausted_reason(state, contract, include_iterations=state["status"] != "WAITING_TRIGGER")
		if state["status"] in ACTIVE_STATUSES | {"WAITING_TRIGGER"} and reason:
			state["status"] = "BUDGET_EXHAUSTED"
			state["last_outcome"] = reason
		if state["status"] in TERMINAL_STATUSES:
			drop_queued_trigger(state, "Pending delivery dropped because the loop became terminal")
		persist_state(state_path, state, contract, digest, raw)
		result = state_summary(state, contract, state_path)
		result.update({"result": "ITERATION_RECORDED", "outcome": args.outcome, "verifier_receipts": verifier_receipts})
		return result


def control_runtime(args: argparse.Namespace, action: str) -> dict[str, Any]:
	project, contract, digest, state_path = load_context(args)
	note = normalized_note(getattr(args, "note", ""), "note")
	with target_file_lock(state_path):
		state, raw = read_state(state_path, contract, digest)
		require_revision(state, args.expected_revision)
		if action == "pause":
			if state["status"] != "ACTIVE":
				fail("PAUSE_INVALID", f"Only ACTIVE loops can pause; current status is {state['status']}")
			state["status"] = "PAUSED"
			append_event(state, "pause", note=note)
		elif action == "resume":
			if state["status"] != "PAUSED":
				fail("RESUME_INVALID", f"Only PAUSED loops can resume; current status is {state['status']}")
			verify_runtime_binding(project, state)
			reason = exhausted_reason(state, contract) if state["active_claim"] is None else ""
			if reason:
				state["status"] = "BUDGET_EXHAUSTED"
				state["last_outcome"] = reason
				drop_queued_trigger(state, "Pending delivery dropped because the resumed loop exhausted its budget")
			else:
				state["status"] = "ACTIVE"
			append_event(state, "resume")
		else:
			if state["status"] in TERMINAL_STATUSES:
				fail("CANCEL_INVALID", f"Loop is already terminal: {state['status']}")
			claim = state["active_claim"]
			state["active_claim"] = None
			state["status"] = "CANCELLED"
			state["last_outcome"] = "cancelled"
			drop_queued_trigger(state, "Pending delivery dropped by cancellation")
			append_event(
				state, "cancel", claim_id=claim["claim_id"] if claim else "",
				claim_digest=claim["claim_digest"] if claim else "", note=note,
			)
		persist_state(state_path, state, contract, digest, raw)
		result = state_summary(state, contract, state_path)
		result["result"] = {"pause": "LOOP_PAUSED", "resume": "LOOP_RESUMED", "cancel": "LOOP_CANCELLED"}[action]
		return result


def recover_runtime(args: argparse.Namespace) -> dict[str, Any]:
	project, contract, digest, state_path = load_context(args)
	note = normalized_note(args.note, "note")
	if not note:
		fail("NOTE_REQUIRED", "Recovery requires a non-empty reason")
	with target_file_lock(state_path):
		state, raw = read_state(state_path, contract, digest)
		require_revision(state, args.expected_revision)
		claim = state["active_claim"]
		if claim is None or claim["claim_id"] != args.claim_id:
			fail("CLAIM_MISMATCH", "Recovery claim ID does not match the active lease")
		if args.action == "continue":
			verify_runtime_binding(project, state)
		age = int((datetime.now(timezone.utc) - parse_time(claim["claimed_at"])).total_seconds())
		timeout = contract["budgets"]["max_iteration_seconds"]
		if age < timeout:
			fail("CLAIM_NOT_STALE", f"Claim age {max(0, age)}s is below iteration timeout {timeout}s")
		was_paused = state["status"] == "PAUSED"
		state["active_claim"] = None
		state["consecutive_failures"] += 1
		state["last_outcome"] = f"stale-{args.action}"
		if args.action == "blocked" or state["consecutive_failures"] >= contract["budgets"]["max_consecutive_failures"]:
			state["status"] = "BLOCKED"
		elif args.action == "cancelled":
			state["status"] = "CANCELLED"
		else:
			state["status"] = "PAUSED" if was_paused else "ACTIVE"
		append_event(
			state, "recover", claim_id=claim["claim_id"], claim_digest=claim["claim_digest"],
			source_revision=claim["source_revision"], outcome=f"stale-{args.action}", note=note,
		)
		if state["status"] in ACTIVE_STATUSES and exhausted_reason(state, contract):
			state["status"] = "BUDGET_EXHAUSTED"
		if state["status"] in TERMINAL_STATUSES:
			drop_queued_trigger(state, "Pending delivery dropped during terminal recovery")
		persist_state(state_path, state, contract, digest, raw)
		result = state_summary(state, contract, state_path)
		result.update({"result": "STALE_ITERATION_RECOVERED", "action": args.action, "age_seconds": age})
		return result


def main() -> int:
	configure_utf8_stdio()
	args = parse_args()
	try:
		if args.command == "start":
			result = start_runtime(args)
		elif args.command == "status":
			result = status_runtime(args)
		elif args.command == "trigger":
			result = trigger_runtime(args)
		elif args.command == "claim":
			result = claim_runtime(args)
		elif args.command == "finish":
			result = finish_runtime(args)
		elif args.command in {"pause", "resume", "cancel"}:
			result = control_runtime(args, args.command)
		else:
			result = recover_runtime(args)
		print(json.dumps(result, ensure_ascii=False, indent=2))
		return 0
	except LoopRuntimeError as exc:
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
