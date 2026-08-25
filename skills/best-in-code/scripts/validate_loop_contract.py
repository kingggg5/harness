#!/usr/bin/env python3
"""Fail-closed structural validator for optional Harness loop contracts."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
from pathlib import Path, PurePosixPath
from typing import Any

sys.dont_write_bytecode = True


MAX_BYTES = 256 * 1024
MAX_LIST_ITEMS = 64
MAX_TEXT_BYTES = 2048
ROOT_FIELDS = {
	"schema_version", "loop_id", "project_id", "run_id", "level", "trigger",
	"objective", "verifiers", "budgets", "control", "evidence",
}
TRIGGER_FIELDS = {"type", "spec", "dedupe_key", "overlap_policy", "max_runs"}
OBJECTIVE_FIELDS = {"outcome", "baseline", "done_when", "excluded_scope"}
VERIFIER_FIELDS = {"id", "kind", "argv", "success", "evidence_path"}
BUDGET_FIELDS = {
	"max_iterations", "max_elapsed_seconds", "max_tokens", "max_cost_microusd",
	"max_external_calls", "max_consecutive_failures", "no_progress_cycles", "max_parallel",
}
CONTROL_FIELDS = {
	"execution_strategy", "graph_id", "read_scope", "write_scope", "side_effect",
	"human_gates", "rollback_revision",
}
EVIDENCE_FIELDS = {"progress_path", "best_artifact_path", "usage_path"}
LEVELS = {"turn", "goal", "scheduled", "proactive"}
TRIGGERS = {"human", "schedule", "event"}
OVERLAP_POLICIES = {"reject", "skip", "queue-one"}
VERIFIER_KINDS = {"deterministic", "judge", "human"}
EXECUTION_STRATEGIES = {"single-owner", "task-graph"}
SIDE_EFFECTS = {"none", "reversible", "consequential"}
HUMAN_GATES = {
	"scope-change", "budget-change", "architecture-change", "consequential-action", "push", "merge",
	"deploy", "publish", "delete", "permission-change", "paid-call",
}
REQUIRED_GATES = {"scope-change", "budget-change", "architecture-change", "consequential-action"}
ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
PROJECT_ID_PATTERN = re.compile(r"^project-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")
DEDUPE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
COMMIT_PATTERN = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
SHELL_PROGRAMS = {"sh", "bash", "zsh", "fish", "cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh", "pwsh.exe"}
INLINE_INTERPRETERS = {"python", "python3", "node", "node.exe", "ruby", "perl"}
SHELL_FLAGS = {"-c", "/c", "-command", "-encodedcommand"}
INLINE_FLAGS = {"-c", "-e", "--eval"}


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Validate a bounded Harness LOOP-CONTRACT.json")
	parser.add_argument("--contract", required=True, help="Path to LOOP-CONTRACT.json")
	parser.add_argument("--json", action="store_true", help="Print structured output")
	return parser.parse_args()


def is_int(value: Any, low: int, high: int) -> bool:
	return isinstance(value, int) and not isinstance(value, bool) and low <= value <= high


def check_closed_object(value: Any, fields: set[str], label: str, errors: list[str]) -> dict[str, Any] | None:
	if not isinstance(value, dict):
		errors.append(f"{label} must be an object")
		return None
	missing = fields - set(value)
	unknown = set(value) - fields
	if missing:
		errors.append(f"{label} is missing fields: {sorted(missing)}")
	if unknown:
		errors.append(f"{label} has unknown fields: {sorted(unknown)}")
	return value if not missing else None


def check_text(value: Any, label: str, errors: list[str], *, max_bytes: int = MAX_TEXT_BYTES) -> str:
	if not isinstance(value, str) or not value.strip() or len(value.encode("utf-8")) > max_bytes or "\x00" in value:
		errors.append(f"{label} must be a non-empty string of at most {max_bytes} UTF-8 bytes")
		return ""
	return value


def check_string_list(value: Any, label: str, errors: list[str], *, allow_empty: bool = True, unique: bool = True) -> list[str]:
	if not isinstance(value, list) or (not allow_empty and not value):
		errors.append(f"{label} must be {'a non-empty' if not allow_empty else 'an'} array of strings")
		return []
	if len(value) > MAX_LIST_ITEMS:
		errors.append(f"{label} must contain at most {MAX_LIST_ITEMS} entries")
		return []
	if any(not isinstance(item, str) or not item.strip() or len(item.encode("utf-8")) > 512 or "\x00" in item or "\n" in item or "\r" in item for item in value):
		errors.append(f"{label} entries must be one-line non-empty strings of at most 512 UTF-8 bytes")
		return []
	if unique and len(value) != len(set(value)):
		errors.append(f"{label} entries must be unique")
	return value


def valid_scope(value: str) -> bool:
	if "\\" in value or "*" in value or "?" in value or "[" in value:
		return False
	path = PurePosixPath(value)
	return not path.is_absolute() and value not in {"", "/"} and ".." not in path.parts


def valid_harness_path(value: str) -> bool:
	if "\\" in value or not value.startswith(".harness/"):
		return False
	path = PurePosixPath(value)
	return not path.is_absolute() and ".." not in path.parts and len(value.encode("utf-8")) <= 512


def executable_name(value: str) -> str:
	return PurePosixPath(value.replace("\\", "/")).name.lower()


def identifier_binds(key: str, identifier: str) -> bool:
	return key == identifier or any(
		key.startswith(f"{identifier}{separator}") or key.endswith(f"{separator}{identifier}") or f"{separator}{identifier}{separator}" in key
		for separator in (":", ".", "_")
	)


def validate_argv(argv: Any, label: str, errors: list[str], kind: str) -> list[str]:
	if kind == "human":
		if argv != []:
			errors.append(f"{label} must be empty for a human verifier")
		return []
	items = check_string_list(argv, label, errors, allow_empty=False, unique=False)
	if not items:
		return []
	program = executable_name(items[0])
	flags = {item.lower() for item in items[1:]}
	if program in SHELL_PROGRAMS and flags & SHELL_FLAGS:
		errors.append(f"{label} cannot invoke a shell command string; call a reviewed script with argv")
	if program in INLINE_INTERPRETERS and flags & INLINE_FLAGS:
		errors.append(f"{label} cannot execute inline code; call a reviewed repository script")
	return items


def validate_contract(data: Any) -> list[str]:
	errors: list[str] = []
	root = check_closed_object(data, ROOT_FIELDS, "contract", errors)
	if root is None:
		return errors
	if root["schema_version"] != 1:
		errors.append("schema_version must be 1")
	loop_id = root["loop_id"]
	if not isinstance(loop_id, str) or not ID_PATTERN.fullmatch(loop_id):
		errors.append("loop_id must match ^[a-z][a-z0-9-]{0,63}$")
	project_id = root["project_id"]
	run_id = root["run_id"]
	if not isinstance(project_id, str) or (project_id and not PROJECT_ID_PATTERN.fullmatch(project_id)):
		errors.append("project_id must be empty in the starter template or a canonical Harness Project ID")
	if not isinstance(run_id, str) or (run_id and not RUN_ID_PATTERN.fullmatch(run_id)):
		errors.append("run_id must be empty in the starter template or a safe Run ID")
	if isinstance(project_id, str) and isinstance(run_id, str) and bool(project_id) != bool(run_id):
		errors.append("project_id and run_id must either both be empty or both bind the active run")
	level = root["level"]
	if not isinstance(level, str) or level not in LEVELS:
		errors.append(f"level must be one of {sorted(LEVELS)}")
		level = ""

	trigger = check_closed_object(root["trigger"], TRIGGER_FIELDS, "trigger", errors)
	if trigger is not None:
		trigger_type = trigger["type"]
		if not isinstance(trigger_type, str) or trigger_type not in TRIGGERS:
			errors.append(f"trigger.type must be one of {sorted(TRIGGERS)}")
			trigger_type = ""
		check_text(trigger["spec"], "trigger.spec", errors, max_bytes=512)
		if not isinstance(trigger["dedupe_key"], str) or not DEDUPE_PATTERN.fullmatch(trigger["dedupe_key"]):
			errors.append("trigger.dedupe_key must be a safe 1 to 256 character identifier")
		else:
			if isinstance(loop_id, str) and ID_PATTERN.fullmatch(loop_id) and not identifier_binds(trigger["dedupe_key"], loop_id):
				errors.append("trigger.dedupe_key must bind loop_id as an identifier")
			if isinstance(run_id, str) and run_id and RUN_ID_PATTERN.fullmatch(run_id) and not identifier_binds(trigger["dedupe_key"], run_id):
				errors.append("an active contract trigger.dedupe_key must bind run_id as an identifier")
		if not isinstance(trigger["overlap_policy"], str) or trigger["overlap_policy"] not in OVERLAP_POLICIES:
			errors.append(f"trigger.overlap_policy must be one of {sorted(OVERLAP_POLICIES)}")
		if not is_int(trigger["max_runs"], 1, 1000):
			errors.append("trigger.max_runs must be an integer from 1 to 1000")
		if level in {"turn", "goal"} and trigger_type != "human":
			errors.append(f"{level} level requires a human trigger")
		if level in {"turn", "goal"} and trigger["max_runs"] != 1:
			errors.append(f"{level} level requires trigger.max_runs=1")
		if level == "scheduled" and trigger_type != "schedule":
			errors.append("scheduled level requires a schedule trigger")
		if level == "proactive" and trigger_type not in {"schedule", "event"}:
			errors.append("proactive level requires a schedule or event trigger")
		if trigger_type == "human" and trigger["overlap_policy"] != "reject":
			errors.append("human triggers require overlap_policy=reject")

	objective = check_closed_object(root["objective"], OBJECTIVE_FIELDS, "objective", errors)
	if objective is not None:
		check_text(objective["outcome"], "objective.outcome", errors)
		check_text(objective["baseline"], "objective.baseline", errors)
		check_string_list(objective["done_when"], "objective.done_when", errors, allow_empty=False)
		check_string_list(objective["excluded_scope"], "objective.excluded_scope", errors, allow_empty=False)

	verifiers = root["verifiers"]
	verifier_ids: set[str] = set()
	verifier_evidence_paths: set[str] = set()
	deterministic_count = 0
	if not isinstance(verifiers, list) or not 1 <= len(verifiers) <= 32:
		errors.append("verifiers must contain 1 to 32 entries")
	else:
		for index, verifier_value in enumerate(verifiers):
			label = f"verifiers[{index}]"
			verifier = check_closed_object(verifier_value, VERIFIER_FIELDS, label, errors)
			if verifier is None:
				continue
			verifier_id = verifier["id"]
			if not isinstance(verifier_id, str) or not ID_PATTERN.fullmatch(verifier_id):
				errors.append(f"{label}.id is invalid")
			elif verifier_id in verifier_ids:
				errors.append(f"duplicate verifier id: {verifier_id}")
			else:
				verifier_ids.add(verifier_id)
			kind = verifier["kind"]
			if not isinstance(kind, str) or kind not in VERIFIER_KINDS:
				errors.append(f"{label}.kind must be one of {sorted(VERIFIER_KINDS)}")
				kind = ""
			if kind == "deterministic":
				deterministic_count += 1
			validate_argv(verifier["argv"], f"{label}.argv", errors, kind)
			check_text(verifier["success"], f"{label}.success", errors, max_bytes=1024)
			if not isinstance(verifier["evidence_path"], str) or not valid_harness_path(verifier["evidence_path"]):
				errors.append(f"{label}.evidence_path must be a safe project-relative path under .harness")
			elif verifier["evidence_path"] in verifier_evidence_paths:
				errors.append(f"{label}.evidence_path duplicates another verifier receipt")
			else:
				verifier_evidence_paths.add(verifier["evidence_path"])
	if deterministic_count == 0:
		errors.append("at least one deterministic verifier is required; judge/human review may supplement it")

	budgets = check_closed_object(root["budgets"], BUDGET_FIELDS, "budgets", errors)
	if budgets is not None:
		ranges = {
			"max_iterations": (1, 100),
			"max_elapsed_seconds": (1, 604800),
			"max_tokens": (1, 1_000_000_000),
			"max_cost_microusd": (0, 1_000_000_000_000),
			"max_external_calls": (0, 10000),
			"max_consecutive_failures": (1, 3),
			"no_progress_cycles": (1, 2),
			"max_parallel": (1, 8),
		}
		for field, (low, high) in ranges.items():
			if not is_int(budgets[field], low, high):
				errors.append(f"budgets.{field} must be an integer from {low} to {high}")
		if is_int(budgets["max_iterations"], 1, 100):
			if isinstance(budgets["max_consecutive_failures"], int) and budgets["max_consecutive_failures"] > budgets["max_iterations"]:
				errors.append("budgets.max_consecutive_failures cannot exceed max_iterations")
			if isinstance(budgets["no_progress_cycles"], int) and budgets["no_progress_cycles"] > budgets["max_iterations"]:
				errors.append("budgets.no_progress_cycles cannot exceed max_iterations")

	control = check_closed_object(root["control"], CONTROL_FIELDS, "control", errors)
	if control is not None:
		strategy = control["execution_strategy"]
		if not isinstance(strategy, str) or strategy not in EXECUTION_STRATEGIES:
			errors.append(f"control.execution_strategy must be one of {sorted(EXECUTION_STRATEGIES)}")
			strategy = ""
		graph_id = control["graph_id"]
		if not isinstance(graph_id, str) or (graph_id and not ID_PATTERN.fullmatch(graph_id)):
			errors.append("control.graph_id must be empty or a safe graph ID")
		if strategy == "task-graph" and not graph_id:
			errors.append("task-graph execution requires control.graph_id")
		if strategy == "single-owner" and graph_id:
			errors.append("single-owner execution cannot declare control.graph_id")
		for field in ("read_scope", "write_scope"):
			values = check_string_list(control[field], f"control.{field}", errors, allow_empty=field == "write_scope")
			for value in values:
				if not valid_scope(value):
					errors.append(f"control.{field} contains unsafe or ambiguous scope: {value!r}")
		if not isinstance(control["side_effect"], str) or control["side_effect"] not in SIDE_EFFECTS:
			errors.append(f"control.side_effect must be one of {sorted(SIDE_EFFECTS)}")
		gates = check_string_list(control["human_gates"], "control.human_gates", errors, allow_empty=False)
		unknown_gates = set(gates) - HUMAN_GATES
		if unknown_gates:
			errors.append(f"control.human_gates contains unknown gates: {sorted(unknown_gates)}")
		missing_gates = REQUIRED_GATES - set(gates)
		if missing_gates:
			errors.append(f"control.human_gates is missing mandatory gates: {sorted(missing_gates)}")
		rollback = control["rollback_revision"]
		if not isinstance(rollback, str) or (rollback and not COMMIT_PATTERN.fullmatch(rollback)):
			errors.append("control.rollback_revision must be empty in the starter or an exact lowercase commit ID")
		if project_id and control["write_scope"] and not rollback:
			errors.append("an active writing loop requires an exact control.rollback_revision")
		if level in {"scheduled", "proactive"} and control["side_effect"] == "consequential":
			errors.append(f"{level} loops cannot directly own consequential effects; stop at a human gate")
		if budgets is not None and isinstance(budgets.get("max_parallel"), int) and budgets["max_parallel"] > 1 and strategy != "task-graph":
			errors.append("budgets.max_parallel greater than 1 requires task-graph execution")

	evidence = check_closed_object(root["evidence"], EVIDENCE_FIELDS, "evidence", errors)
	if evidence is not None:
		paths: list[str] = []
		for field in sorted(EVIDENCE_FIELDS):
			value = evidence[field]
			if not isinstance(value, str) or not valid_harness_path(value):
				errors.append(f"evidence.{field} must be a safe project-relative path under .harness")
			else:
				paths.append(value)
		if len(paths) != len(set(paths)):
			errors.append("evidence paths must be distinct")
		for path in paths:
			if path in verifier_evidence_paths:
				errors.append(f"evidence path collides with a verifier receipt: {path}")
	return errors


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
	result: dict[str, Any] = {}
	for key, value in pairs:
		if key in result:
			raise ValueError(f"duplicate JSON key: {key}")
		result[key] = value
	return result


def load_contract(path: Path) -> tuple[Any, list[str]]:
	errors: list[str] = []
	try:
		if path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)()):
			return None, [f"contract cannot be a symlink or junction: {path}"]
		initial = path.lstat()
		if not stat.S_ISREG(initial.st_mode) or initial.st_nlink > 1:
			return None, [f"contract must be one regular non-hard-linked file: {path}"]
		if initial.st_size > MAX_BYTES:
			return None, [f"contract exceeds {MAX_BYTES} bytes"]
		flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOINHERIT", 0) | getattr(os, "O_NOFOLLOW", 0)
		descriptor = os.open(path, flags)
		try:
			metadata = os.fstat(descriptor)
			if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink > 1:
				return None, [f"contract must be one regular non-hard-linked file: {path}"]
			if (initial.st_dev, initial.st_ino) != (metadata.st_dev, metadata.st_ino):
				return None, [f"contract changed while opening: {path}"]
			if metadata.st_size > MAX_BYTES:
				return None, [f"contract exceeds {MAX_BYTES} bytes"]
			chunks: list[bytes] = []
			remaining = MAX_BYTES + 1
			while remaining > 0:
				chunk = os.read(descriptor, min(64 * 1024, remaining))
				if not chunk:
					break
				chunks.append(chunk)
				remaining -= len(chunk)
			raw = b"".join(chunks)
		finally:
			os.close(descriptor)
		if len(raw) > MAX_BYTES:
			return None, [f"contract exceeds {MAX_BYTES} bytes"]
		data = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
	except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError, MemoryError) as exc:
		return None, [f"could not read contract: {exc}"]
	return data, errors


def main() -> int:
	args = parse_args()
	path = Path(args.contract)
	data, errors = load_contract(path)
	if not errors:
		errors = validate_contract(data)
	result = {"ok": not errors, "contract": str(path), "errors": errors}
	if args.json:
		print(json.dumps(result, ensure_ascii=False, indent=2))
	elif errors:
		print("Harness loop-contract validation failed:", file=sys.stderr)
		for error in errors:
			print(f"- {error}", file=sys.stderr)
	else:
		print("Harness loop-contract validation passed.")
	return 0 if not errors else 1


if __name__ == "__main__":
	raise SystemExit(main())
