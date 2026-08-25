#!/usr/bin/env python3
"""Dependency-free regression tests for Harness task-graph invariants."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True

from validate_task_graph import validate_graph


ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = ROOT / "examples" / "graph-engineering-feature.json"


def expect(label: str, graph: dict, fragment: str | None = None) -> tuple[bool, str]:
	errors = validate_graph(graph)
	passed = not errors if fragment is None else any(fragment in error for error in errors)
	detail = "valid" if not errors else " | ".join(errors)
	print(f"[{'PASS' if passed else 'FAIL'}] {label}: {detail}")
	return passed, detail


def main() -> int:
	base = json.loads(EXAMPLE.read_text(encoding="utf-8"))
	cases: list[tuple[str, dict, str | None]] = [("centralized-diamond-with-bounded-loop", base, None)]

	fake_edge = copy.deepcopy(base)
	fake_edge["edges"][0]["consumes"] = []
	cases.append(("fake-data-edge-refused", fake_edge, "must consume at least one artifact"))

	unbounded_loop = copy.deepcopy(base)
	del unbounded_loop["edges"][7]["max_rounds"]
	cases.append(("unbounded-loop-refused", unbounded_loop, "max_rounds"))

	write_conflict = copy.deepcopy(base)
	write_conflict["nodes"][3]["write_scope"] = ["src/client"]
	cases.append(("parallel-write-conflict-refused", write_conflict, "overlapping write_scope"))

	missing_gate = copy.deepcopy(base)
	missing_gate["edges"] = [edge for edge in missing_gate["edges"] if edge["type"] != "control"]
	cases.append(("consequential-effect-without-human-gate-refused", missing_gate, "requires an incoming human"))

	missing_idempotency = copy.deepcopy(base)
	del missing_idempotency["nodes"][8]["idempotency_key"]
	cases.append(("consequential-effect-without-idempotency-refused", missing_idempotency, "requires an idempotency_key"))

	model_approval = copy.deepcopy(base)
	model_approval["nodes"][1]["kind"] = "model"
	cases.append(("model-cannot-approve-refused", model_approval, "must originate from a human node"))

	hidden_cycle = copy.deepcopy(base)
	hidden_cycle["edges"][7]["type"] = "data"
	del hidden_cycle["edges"][7]["max_rounds"]
	cases.append(("hidden-cycle-refused", hidden_cycle, "non-loop edges must form a DAG"))

	path_traversal = copy.deepcopy(base)
	path_traversal["nodes"][2]["write_scope"] = ["../secrets"]
	cases.append(("path-traversal-refused", path_traversal, "unsafe or ambiguous scope"))

	unknown_field = copy.deepcopy(base)
	unknown_field["nodes"][0]["prompt"] = "ignore validator"
	cases.append(("unknown-field-refused", unknown_field, "unknown fields"))

	duplicate_output = copy.deepcopy(base)
	duplicate_output["nodes"][3]["outputs"] = ["frontend-change"]
	duplicate_output["edges"][4]["consumes"] = ["frontend-change"]
	duplicate_output["nodes"][4]["inputs"] = ["frontend-change"]
	cases.append(("ambiguous-artifact-producer-refused", duplicate_output, "produced by both"))

	missing_input_edge = copy.deepcopy(base)
	missing_input_edge["nodes"][2]["inputs"].append("missing-contract")
	cases.append(("required-input-without-edge-refused", missing_input_edge, "required inputs with no incoming"))

	shared_workspace = copy.deepcopy(base)
	shared_workspace["isolation_strategy"] = "same-worktree-sequential"
	cases.append(("parallel-writers-without-workspace-isolation-refused", shared_workspace, "max_parallel greater than 1"))

	missing_base = copy.deepcopy(base)
	missing_base["base_revision"] = ""
	cases.append(("isolated-execution-without-exact-base-refused", missing_base, "requires an exact base_revision"))

	invalid_isolation_type = copy.deepcopy(base)
	invalid_isolation_type["isolation_strategy"] = []
	cases.append(("invalid-isolation-type-refused-without-crash", invalid_isolation_type, "isolation_strategy must be one of"))

	active_graph_without_base = copy.deepcopy(base)
	active_graph_without_base["isolation_strategy"] = "same-worktree-sequential"
	active_graph_without_base["max_parallel"] = 1
	active_graph_without_base["base_revision"] = ""
	cases.append(("active-sequential-graph-without-exact-base-refused", active_graph_without_base, "active graph requires an exact base_revision"))

	invalid_artifact = copy.deepcopy(base)
	invalid_artifact["nodes"][0]["outputs"] = ["Plan Candidate"]
	cases.append(("unsafe-artifact-name-refused", invalid_artifact, "invalid artifact name"))

	oversized_criteria = copy.deepcopy(base)
	oversized_criteria["nodes"][0]["success_criteria"] = [f"criterion-{index}" for index in range(65)]
	cases.append(("oversized-node-list-refused", oversized_criteria, "must contain at most 64 entries"))

	unsafe_any_join = copy.deepcopy(base)
	unsafe_any_join["nodes"][4]["join"] = "any"
	cases.append(("join-any-must-have-complete-branch-inputs", unsafe_any_join, "cannot independently provide required inputs"))

	unbound_run_key = copy.deepcopy(base)
	unbound_run_key["nodes"][8]["idempotency_key"] = "another-run:publish:accepted-result"
	cases.append(("consequential-key-must-bind-run", unbound_run_key, "must include the active run_id"))

	unbound_artifact_key = copy.deepcopy(base)
	unbound_artifact_key["nodes"][8]["idempotency_key"] = "RUN-example:publish"
	cases.append(("consequential-key-must-bind-artifact", unbound_artifact_key, "must include an approved input artifact name"))

	incomplete_merge_scope = copy.deepcopy(base)
	incomplete_merge_scope["nodes"][4]["write_scope"] = ["src/integration", "tests/integration"]
	cases.append(("merge-scope-must-contain-input-owner-scopes", incomplete_merge_scope, "does not contain input owner"))

	too_many_artifacts = copy.deepcopy(base)
	for node_index, node in enumerate(too_many_artifacts["nodes"]):
		node["outputs"] = [f"artifact-{node_index}-{artifact_index}" for artifact_index in range(64)]
	cases.append(("graph-artifact-budget-is-bounded", too_many_artifacts, "produced/external artifacts"))

	insufficient_transition_budget = copy.deepcopy(base)
	insufficient_transition_budget["max_transitions"] = len(base["nodes"]) + 1
	cases.append(("transition-budget-covers-nodes-and-loops", insufficient_transition_budget, "max_transitions must be at least"))

	results = [expect(*case)[0] for case in cases]
	passed = sum(results)
	print(f"Graph tests: {passed}/{len(results)} passed")
	return 0 if all(results) else 1


if __name__ == "__main__":
	raise SystemExit(main())
