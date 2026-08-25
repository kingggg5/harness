#!/usr/bin/env python3
"""Dependency-free regression tests for Harness loop-contract invariants."""

from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True

from validate_loop_contract import MAX_BYTES, load_contract, validate_contract


ROOT = Path(__file__).resolve().parents[3]
TEMPLATE = ROOT / "skills" / "best-in-code" / "assets" / "templates" / "LOOP-CONTRACT.json"


def expect(label: str, contract: dict, fragment: str | None = None) -> bool:
	errors = validate_contract(contract)
	passed = not errors if fragment is None else any(fragment in error for error in errors)
	detail = "valid" if not errors else " | ".join(errors)
	print(f"[{'PASS' if passed else 'FAIL'}] {label}: {detail}")
	return passed


def expect_load_failure(label: str, path: Path, fragment: str) -> bool:
	_, errors = load_contract(path)
	passed = any(fragment in error for error in errors)
	print(f"[{'PASS' if passed else 'FAIL'}] {label}: {' | '.join(errors) if errors else 'unexpectedly valid'}")
	return passed


def main() -> int:
	base = json.loads(TEMPLATE.read_text(encoding="utf-8"))
	cases: list[tuple[str, dict, str | None]] = [("bounded-human-goal", base, None)]

	unknown_field = copy.deepcopy(base)
	unknown_field["prompt"] = "keep going"
	cases.append(("unknown-root-field-refused", unknown_field, "unknown fields"))

	missing_field = copy.deepcopy(base)
	del missing_field["budgets"]
	cases.append(("missing-root-field-refused", missing_field, "missing fields"))

	missing_baseline = copy.deepcopy(base)
	del missing_baseline["objective"]["baseline"]
	cases.append(("missing-baseline-refused", missing_baseline, "objective is missing fields"))

	scheduled = copy.deepcopy(base)
	scheduled["level"] = "scheduled"
	scheduled["trigger"].update({"type": "schedule", "spec": "every 30 minutes", "overlap_policy": "skip", "max_runs": 48})
	cases.append(("bounded-scheduled-loop", scheduled, None))

	proactive = copy.deepcopy(base)
	proactive["level"] = "proactive"
	proactive["trigger"].update({"type": "event", "spec": "github.pull_request.opened", "overlap_policy": "queue-one", "max_runs": 100})
	cases.append(("bounded-proactive-event-loop", proactive, None))

	wrong_trigger = copy.deepcopy(base)
	wrong_trigger["level"] = "scheduled"
	cases.append(("scheduled-requires-schedule-trigger", wrong_trigger, "requires a schedule trigger"))

	unbounded_runs = copy.deepcopy(scheduled)
	unbounded_runs["trigger"]["max_runs"] = 0
	cases.append(("open-ended-schedule-refused", unbounded_runs, "max_runs"))

	bad_dedupe = copy.deepcopy(base)
	bad_dedupe["trigger"]["dedupe_key"] = "another-loop"
	cases.append(("dedupe-key-binds-loop", bad_dedupe, "must bind loop_id"))

	malformed_types = copy.deepcopy(base)
	malformed_types["level"] = []
	malformed_types["trigger"]["type"] = []
	malformed_types["trigger"]["overlap_policy"] = []
	malformed_types["verifiers"][0]["kind"] = []
	malformed_types["control"]["execution_strategy"] = []
	malformed_types["control"]["side_effect"] = []
	cases.append(("malformed-nested-types-refused-without-crash", malformed_types, "level must be one of"))

	human_only = copy.deepcopy(base)
	human_only["verifiers"] = [{"id": "review", "kind": "human", "command_id": "", "success": "Human accepts evidence.", "evidence_path": ".harness/evidence/review.json"}]
	cases.append(("human-review-cannot-replace-deterministic-check", human_only, "deterministic verifier"))

	judge_only = copy.deepcopy(base)
	judge_only["verifiers"][0]["kind"] = "judge"
	cases.append(("judge-cannot-be-only-verifier", judge_only, "deterministic verifier"))

	raw_command = copy.deepcopy(base)
	raw_command["verifiers"][0]["argv"] = ["git", "push", "--force"]
	cases.append(("raw-verifier-command-refused", raw_command, "unknown fields"))

	unsafe_command_id = copy.deepcopy(base)
	unsafe_command_id["verifiers"][0]["command_id"] = "git push --force"
	cases.append(("unsafe-command-id-refused", unsafe_command_id, "trusted verifier capability"))

	missing_command_id = copy.deepcopy(base)
	del missing_command_id["verifiers"][0]["command_id"]
	cases.append(("missing-command-id-refused", missing_command_id, "missing fields"))

	human_command = copy.deepcopy(base)
	human_command["verifiers"].append({"id": "review", "kind": "human", "command_id": "review-command", "success": "Human accepts evidence.", "evidence_path": ".harness/evidence/review.json"})
	cases.append(("human-verifier-cannot-run-command", human_command, "must be empty for a human verifier"))

	duplicate_verifier = copy.deepcopy(base)
	duplicate_verifier["verifiers"].append(copy.deepcopy(duplicate_verifier["verifiers"][0]))
	cases.append(("duplicate-verifier-id-refused", duplicate_verifier, "duplicate verifier id"))

	duplicate_evidence = copy.deepcopy(base)
	duplicate_evidence["verifiers"].append({"id": "second", "kind": "deterministic", "command_id": "second-check", "success": "The second check passes.", "evidence_path": duplicate_evidence["verifiers"][0]["evidence_path"]})
	cases.append(("verifier-evidence-collision-refused", duplicate_evidence, "duplicates another verifier receipt"))

	unsafe_evidence = copy.deepcopy(base)
	unsafe_evidence["verifiers"][0]["evidence_path"] = "../pass.json"
	cases.append(("evidence-path-escape-refused", unsafe_evidence, "safe project-relative path"))

	too_many_iterations = copy.deepcopy(base)
	too_many_iterations["budgets"]["max_iterations"] = 101
	cases.append(("iteration-budget-bounded", too_many_iterations, "max_iterations"))

	failures_exceed_iterations = copy.deepcopy(base)
	failures_exceed_iterations["budgets"].update({"max_iterations": 2, "max_consecutive_failures": 3})
	cases.append(("failure-stop-within-iteration-budget", failures_exceed_iterations, "cannot exceed max_iterations"))

	no_progress_exceeds_iterations = copy.deepcopy(base)
	no_progress_exceeds_iterations["budgets"].update({"max_iterations": 1, "max_consecutive_failures": 1, "no_progress_cycles": 2})
	cases.append(("no-progress-stop-within-iteration-budget", no_progress_exceeds_iterations, "cannot exceed max_iterations"))

	parallel_single_owner = copy.deepcopy(base)
	parallel_single_owner["budgets"]["max_parallel"] = 2
	cases.append(("parallel-loop-requires-task-graph", parallel_single_owner, "requires task-graph"))

	graph_without_id = copy.deepcopy(base)
	graph_without_id["control"]["execution_strategy"] = "task-graph"
	cases.append(("task-graph-requires-id", graph_without_id, "requires control.graph_id"))

	graph_loop = copy.deepcopy(base)
	graph_loop["control"].update({"execution_strategy": "task-graph", "graph_id": "delivery-graph"})
	graph_loop["budgets"]["max_parallel"] = 2
	cases.append(("bounded-task-graph-loop", graph_loop, None))

	missing_gate = copy.deepcopy(base)
	missing_gate["control"]["human_gates"].remove("budget-change")
	cases.append(("mandatory-human-gates-preserved", missing_gate, "missing mandatory gates"))

	missing_architecture_gate = copy.deepcopy(base)
	missing_architecture_gate["control"]["human_gates"].remove("architecture-change")
	cases.append(("architecture-remains-human-owned", missing_architecture_gate, "architecture-change"))

	active_writer = copy.deepcopy(base)
	active_writer.update({"project_id": "project-11111111-1111-4111-8111-111111111111", "run_id": "RUN-loop-test"})
	active_writer["control"]["write_scope"] = ["src"]
	active_writer["trigger"]["dedupe_key"] = "replace-me:RUN-loop-test"
	cases.append(("active-writer-requires-rollback", active_writer, "requires an exact control.rollback_revision"))

	active_without_run_dedupe = copy.deepcopy(active_writer)
	active_without_run_dedupe["trigger"]["dedupe_key"] = "replace-me"
	cases.append(("active-dedupe-key-binds-run", active_without_run_dedupe, "must bind run_id"))

	active_writer_with_rollback = copy.deepcopy(active_writer)
	active_writer_with_rollback["control"]["rollback_revision"] = "1" * 40
	cases.append(("active-writer-with-rollback", active_writer_with_rollback, None))

	proactive_consequential = copy.deepcopy(proactive)
	proactive_consequential["control"]["side_effect"] = "consequential"
	cases.append(("proactive-loop-stops-before-consequential-effect", proactive_consequential, "cannot directly own consequential effects"))

	unsafe_scope = copy.deepcopy(base)
	unsafe_scope["control"]["write_scope"] = ["../outside"]
	cases.append(("unsafe-write-scope-refused", unsafe_scope, "unsafe or ambiguous scope"))

	mismatched_identity = copy.deepcopy(base)
	mismatched_identity["project_id"] = "project-11111111-1111-4111-8111-111111111111"
	cases.append(("project-and-run-bind-together", mismatched_identity, "either both be empty"))

	usage_collision = copy.deepcopy(base)
	usage_collision["evidence"]["usage_path"] = usage_collision["evidence"]["progress_path"]
	cases.append(("usage-evidence-path-is-distinct", usage_collision, "evidence paths must be distinct"))

	results = [expect(*case) for case in cases]
	with tempfile.TemporaryDirectory(prefix="harness-loop-tests-") as temp_root:
		root = Path(temp_root)
		duplicate_key = root / "duplicate-key.json"
		duplicate_key.write_text('{"schema_version": 1, "schema_version": 1}', encoding="utf-8")
		results.append(expect_load_failure("duplicate-json-key-refused", duplicate_key, "duplicate JSON key"))
		oversized = root / "oversized.json"
		oversized.write_bytes(b" " * (MAX_BYTES + 1))
		results.append(expect_load_failure("oversized-contract-refused-before-parse", oversized, "exceeds"))
	passed = sum(results)
	print(f"Loop tests: {passed}/{len(results)} passed")
	return 0 if all(results) else 1


if __name__ == "__main__":
	raise SystemExit(main())
