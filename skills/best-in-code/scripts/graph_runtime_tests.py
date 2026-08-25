#!/usr/bin/env python3
"""Integration tests for the optional Harness graph runtime ledger."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.dont_write_bytecode = True


SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[2]
RUNTIME = SCRIPTS / "graph_runtime.py"
INIT = SCRIPTS / "init_project.py"
EXAMPLE = ROOT / "examples" / "graph-engineering-feature.json"
PROJECT_ID = "project-11111111-1111-4111-8111-111111111111"
RUN_ID = "RUN-runtime-test"


class Report:
	def __init__(self) -> None:
		self.passed = 0
		self.failed = 0

	def check(self, name: str, condition: bool, detail: str) -> None:
		detail = re.sub(r"tok_[0-9a-f]{64}", "<redacted-claim-token>", detail)
		detail = detail if len(detail) <= 800 else detail[:797] + "..."
		if condition:
			self.passed += 1
			print(f"[PASS] {name}: {detail}")
		else:
			self.failed += 1
			print(f"[FAIL] {name}: {detail}")


def process(command: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
	merged = os.environ.copy()
	if env:
		merged.update(env)
	return subprocess.run(command, cwd=str(cwd), env=merged, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)


def git(project: Path, *arguments: str) -> str:
	result = process(["git", *arguments], project)
	if result.returncode != 0:
		raise RuntimeError(result.stderr or result.stdout)
	return result.stdout.strip()


def runtime(project: Path, command: str, *arguments: str, env: dict[str, str] | None = None) -> tuple[subprocess.CompletedProcess, dict]:
	base = [
		sys.executable, str(RUNTIME), command,
		"--project", str(project),
		"--graph", ".harness/TASK-GRAPH.json",
	]
	result = process([*base, *arguments], project, env)
	try:
		payload = json.loads(result.stdout)
	except json.JSONDecodeError:
		payload = {"ok": False, "code": "UNPARSEABLE", "error": result.stdout + result.stderr}
	return result, payload


def write_json(path: Path, value: dict) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(value, ensure_ascii=False, indent="\t") + "\n", encoding="utf-8")


def write_text(path: Path, value: str) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(value, encoding="utf-8")


def make_fixture(root: Path) -> tuple[Path, str]:
	project = root / "project"
	project.mkdir()
	git(project, "init", "-b", "main")
	git(project, "config", "user.email", "harness-test@example.invalid")
	git(project, "config", "user.name", "Harness Test")
	for relative in ("src/client/base.txt", "src/server/base.txt", "src/integration/base.txt"):
		write_text(project / relative, "baseline\n")
	git(project, "add", ".")
	git(project, "commit", "-m", "test baseline")
	initialized = process([
		sys.executable, str(INIT), "--project", str(project), "--models", "generic",
		"--project-id", PROJECT_ID, "--json",
	], project)
	if initialized.returncode != 0:
		raise RuntimeError(initialized.stdout + initialized.stderr)
	git(project, "add", ".")
	git(project, "commit", "-m", "initialize harness")
	base = git(project, "rev-parse", "HEAD")
	state_path = project / ".harness" / "STATE.json"
	state = json.loads(state_path.read_text(encoding="utf-8"))
	state.update({"run_id": RUN_ID, "operation": "start", "state": "BUILD"})
	write_json(state_path, state)
	graph = json.loads(EXAMPLE.read_text(encoding="utf-8"))
	graph.update({"project_id": PROJECT_ID, "run_id": RUN_ID, "base_revision": base})
	for node in graph["nodes"]:
		if node["id"] == "plan":
			node["optional_inputs"] = ["extra-context"]
		if node["id"] == "publish":
			node["idempotency_key"] = f"{RUN_ID}:publish:accepted-result"
		if node["id"] == "merge":
			node["timeout_seconds"] = 1
	write_json(project / ".harness" / "TASK-GRAPH.json", graph)
	write_text(project / ".harness" / "inputs" / "request.md", "Build saved filters.\n")
	write_text(project / ".harness" / "inputs" / "repository.md", "Repository evidence.\n")
	return project, base


def create_worker_commit(project: Path, root: Path, branch: str, relative: str, content: str, base: str) -> tuple[Path, str]:
	worktree = root / branch
	git(project, "worktree", "add", "-b", branch, str(worktree), base)
	write_text(worktree / relative, content)
	git(worktree, "add", relative)
	git(worktree, "commit", "-m", branch)
	return worktree, git(worktree, "rev-parse", "HEAD")


def main() -> int:
	report = Report()
	workspace = Path(tempfile.mkdtemp(prefix="harness-graph-runtime-"))
	try:
		project, base = make_fixture(workspace)
		started_result, started = runtime(
			project, "start",
			"--artifact", "request=.harness/inputs/request.md",
			"--artifact", "repository-evidence=.harness/inputs/repository.md",
		)
		report.check("exact-baseline-start", started_result.returncode == 0 and started.get("revision") == 0 and started.get("ready") == ["plan"], str(started))
		report.check("optional-entry-input-can-be-omitted", "extra-context" not in started.get("artifacts", {}), "declared optional seed omission did not block the entry node")

		claim_command = [
			sys.executable, str(RUNTIME), "claim", "--project", str(project),
			"--graph", ".harness/TASK-GRAPH.json", "--node", "plan",
			"--worker", "Planner", "--expected-revision", "0",
		]
		claimers = [subprocess.Popen(claim_command, cwd=str(project), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace") for _ in range(2)]
		claim_results = [claimer.communicate(timeout=120) for claimer in claimers]
		claim_payloads = [json.loads(stdout) for stdout, _ in claim_results]
		winners = [payload for payload in claim_payloads if payload.get("ok")]
		report.check("concurrent-claim-cas", len(winners) == 1 and sorted(payload.get("code", "OK") for payload in claim_payloads) == ["OK", "REVISION_CONFLICT"], str(claim_payloads))
		plan_claim = winners[0]
		ledger_text = Path(started["state_path"]).read_text(encoding="utf-8")
		report.check("raw-claim-token-not-persisted", plan_claim["claim_token"] not in ledger_text, "ledger stores only the claim digest")

		write_text(project / ".harness" / "artifacts" / "plan.json", "{\"plan\":\"bounded\"}\n")
		_, plan_done = runtime(
			project, "finish", "--node", "plan",
			"--outcome", "success", "--artifact", "plan-candidate=.harness/artifacts/plan.json",
			"--expected-revision", "1", env={"HARNESS_GRAPH_CLAIM_TOKEN": plan_claim["claim_token"]},
		)
		report.check("artifact-unlocks-dependent-node", plan_done.get("revision") == 2 and plan_done.get("ready") == ["plan-approval"], str(plan_done))

		_, approval_claim = runtime(project, "claim", "--node", "plan-approval", "--worker", "Human", "--expected-revision", "2")
		write_text(project / ".harness" / "artifacts" / "approved.json", "{\"approved\":true}\n")
		_, approved = runtime(
			project, "finish", "--node", "plan-approval", "--claim-token", approval_claim["claim_token"],
			"--outcome", "approve", "--artifact", "approved-contract=.harness/artifacts/approved.json",
			"--expected-revision", "3",
		)
		report.check("human-gate-fanout", approved.get("revision") == 4 and approved.get("ready") == ["backend", "frontend"], str(approved))

		_, frontend_claim = runtime(project, "claim", "--node", "frontend", "--worker", "Frontend Engineer", "--workspace-revision", base, "--expected-revision", "4")
		_, backend_claim = runtime(project, "claim", "--node", "backend", "--worker", "Backend Engineer", "--workspace-revision", base, "--expected-revision", "5")
		report.check("bounded-parallel-claims", frontend_claim.get("revision") == 5 and backend_claim.get("revision") == 6 and len(backend_claim.get("running", [])) == 2, str(backend_claim))

		_, frontend_commit = create_worker_commit(project, workspace, "runtime-front", "src/client/frontend.txt", "frontend\n", base)
		_, backend_commit = create_worker_commit(project, workspace, "runtime-back", "src/server/backend.txt", "backend\n", base)
		write_text(project / ".harness" / "artifacts" / "frontend.json", "{\"commit\":\"frontend\"}\n")
		write_text(project / ".harness" / "artifacts" / "backend.json", "{\"commit\":\"backend\"}\n")
		_, frontend_done = runtime(
			project, "finish", "--node", "frontend", "--claim-token", frontend_claim["claim_token"],
			"--outcome", "success", "--artifact", "frontend-change=.harness/artifacts/frontend.json",
			"--source-revision", frontend_commit, "--expected-revision", "6",
		)
		bad_result, bad_backend = runtime(
			project, "finish", "--node", "backend", "--claim-token", backend_claim["claim_token"],
			"--outcome", "success", "--artifact", "backend-change=.harness/artifacts/backend.json",
			"--source-revision", frontend_commit, "--expected-revision", "7",
		)
		report.check("write-scope-enforced", frontend_done.get("revision") == 7 and bad_result.returncode != 0 and bad_backend.get("code") == "WRITE_SCOPE_VIOLATION", str(bad_backend))

		_, backend_done = runtime(
			project, "finish", "--node", "backend", "--claim-token", backend_claim["claim_token"],
			"--outcome", "success", "--artifact", "backend-change=.harness/artifacts/backend.json",
			"--source-revision", backend_commit, "--expected-revision", "7",
		)
		report.check("fan-in-ready-after-both-receipts", backend_done.get("revision") == 8 and backend_done.get("ready") == ["merge"], str(backend_done))

		frontend_path = project / ".harness" / "artifacts" / "frontend.json"
		original_frontend = frontend_path.read_text(encoding="utf-8")
		write_text(frontend_path, original_frontend + "drift\n")
		drift_result, drift = runtime(project, "claim", "--node", "merge", "--worker", "Project Manager", "--expected-revision", "8")
		report.check("artifact-drift-refused-at-consumption", drift_result.returncode != 0 and drift.get("code") == "ARTIFACT_DRIFT", str(drift))
		write_text(frontend_path, original_frontend)

		merge_claim_result, merge_claim = runtime(
			project, "claim", "--node", "merge", "--worker", "Project Manager",
			"--expected-revision", "8",
		)
		report.check("merge-claim-before-recovery", merge_claim_result.returncode == 0 and "claim_id" in merge_claim, str(merge_claim))
		if merge_claim_result.returncode != 0:
			print(f"Graph runtime tests: {report.passed} passed, {report.failed} failed")
			return 1
		write_text(project / ".harness" / "artifacts" / "integrated-premature.json", "{\"integrated\":false}\n")
		missing_parent_result, missing_parent = runtime(
			project, "finish", "--node", "merge", "--claim-token", merge_claim["claim_token"],
			"--outcome", "success", "--artifact", "integrated-change=.harness/artifacts/integrated-premature.json",
			"--source-revision", frontend_commit, "--expected-revision", "9",
		)
		report.check("merge-must-contain-every-worker-commit", missing_parent_result.returncode != 0 and missing_parent.get("code") == "REVISION_DIVERGED", str(missing_parent))
		time.sleep(1.1)
		_, recovered = runtime(
			project, "recover", "--node", "merge", "--claim-id", merge_claim["claim_id"],
			"--action", "ready", "--note", "Worker heartbeat expired", "--expected-revision", "9",
		)
		report.check("stale-claim-recovery", recovered.get("revision") == 10 and recovered.get("ready") == ["merge"] and recovered.get("action") == "ready", str(recovered))

		backend_path = project / ".harness" / "artifacts" / "backend.json"
		original_backend = backend_path.read_text(encoding="utf-8")
		write_text(backend_path, original_backend + "drift\n")
		resume_result, resume_drift = runtime(project, "resume")
		report.check("resume-verifies-all-artifacts", resume_result.returncode != 0 and resume_drift.get("code") == "ARTIFACT_DRIFT", str(resume_drift))
		write_text(backend_path, original_backend)
		resume_ok_result, resume_ok = runtime(project, "resume")
		report.check("resume-after-evidence-restored", resume_ok_result.returncode == 0 and resume_ok.get("artifacts_verified") is True, str(resume_ok))

		_, merge_claim_retry = runtime(project, "claim", "--node", "merge", "--worker", "Project Manager", "--expected-revision", "10")
		git(project, "merge", "--no-ff", "runtime-front", "-m", "integrate frontend")
		git(project, "merge", "--no-ff", "runtime-back", "-m", "integrate backend")
		write_text(project / "src" / "integration" / "integrated.txt", "integrated\n")
		git(project, "add", "src/integration/integrated.txt")
		git(project, "commit", "-m", "finish integration")
		merge_commit = git(project, "rev-parse", "HEAD")
		write_text(project / ".harness" / "artifacts" / "integrated.json", "{\"integrated\":true}\n")
		_, merge_done = runtime(
			project, "finish", "--node", "merge", "--claim-token", merge_claim_retry["claim_token"],
			"--outcome", "success", "--artifact", "integrated-change=.harness/artifacts/integrated.json",
			"--source-revision", merge_commit, "--expected-revision", "11",
		)
		report.check("merge-result-contains-worker-commits", merge_done.get("revision") == 12 and merge_done.get("ready") == ["qa"], str(merge_done))

		_, qa_claim = runtime(project, "claim", "--node", "qa", "--worker", "QA", "--expected-revision", "12")
		write_text(project / ".harness" / "artifacts" / "qa-findings.json", "{\"findings\":[\"repair\"]}\n")
		write_text(project / ".harness" / "artifacts" / "qa-report-invalid.json", "{\"passed\":false}\n")
		extra_output_result, extra_output = runtime(
			project, "finish", "--node", "qa", "--claim-token", qa_claim["claim_token"],
			"--outcome", "failure", "--artifact", "qa-findings=.harness/artifacts/qa-findings.json",
			"--artifact", "qa-report=.harness/artifacts/qa-report-invalid.json", "--expected-revision", "13",
		)
		report.check("branch-output-must-match-outcome", extra_output_result.returncode != 0 and extra_output.get("code") == "OUTPUT_NOT_ALLOWED", str(extra_output))
		_, qa_failed = runtime(
			project, "finish", "--node", "qa", "--claim-token", qa_claim["claim_token"],
			"--outcome", "failure", "--artifact", "qa-findings=.harness/artifacts/qa-findings.json",
			"--expected-revision", "13",
		)
		report.check("failure-selects-repair-branch", qa_failed.get("revision") == 14 and qa_failed.get("ready") == ["repair"] and qa_failed.get("nodes", {}).get("acceptance", {}).get("status") == "SKIPPED", str(qa_failed))

		_, repair_claim = runtime(project, "claim", "--node", "repair", "--worker", "Project Manager", "--expected-revision", "14")
		write_text(project / "src" / "client" / "repair.txt", "repair\n")
		git(project, "add", "src/client/repair.txt")
		git(project, "commit", "-m", "repair qa finding")
		repair_commit = git(project, "rev-parse", "HEAD")
		write_text(project / ".harness" / "artifacts" / "repair.json", "{\"repair\":true}\n")
		_, repair_done = runtime(
			project, "finish", "--node", "repair", "--claim-token", repair_claim["claim_token"],
			"--outcome", "success", "--artifact", "repair-set=.harness/artifacts/repair.json",
			"--source-revision", repair_commit, "--expected-revision", "15",
		)
		report.check("bounded-loop-reactivates-qa", repair_done.get("revision") == 16 and repair_done.get("ready") == ["qa"] and repair_done.get("loop_rounds", {}).get("repair->qa") == 1 and repair_done.get("nodes", {}).get("qa", {}).get("activation") == 2, str(repair_done))

		_, qa_retry_claim = runtime(project, "claim", "--node", "qa", "--worker", "QA", "--expected-revision", "16")
		write_text(project / ".harness" / "artifacts" / "qa-report.json", "{\"passed\":true}\n")
		_, qa_passed = runtime(
			project, "finish", "--node", "qa", "--claim-token", qa_retry_claim["claim_token"],
			"--outcome", "success", "--artifact", "qa-report=.harness/artifacts/qa-report.json",
			"--expected-revision", "17",
		)
		report.check("new-loop-outcome-reactivates-skipped-branch", qa_passed.get("revision") == 18 and qa_passed.get("ready") == ["acceptance"] and qa_passed.get("nodes", {}).get("acceptance", {}).get("activation") == 1, str(qa_passed))

		graph_path = project / ".harness" / "TASK-GRAPH.json"
		original_graph = graph_path.read_text(encoding="utf-8")
		graph = json.loads(original_graph)
		graph["nodes"][0]["objective"] = "Changed after start"
		write_json(graph_path, graph)
		changed_result, changed = runtime(project, "status")
		report.check("graph-digest-pin", changed_result.returncode != 0 and changed.get("code") == "STATE_INVALID", str(changed))
		write_text(graph_path, original_graph)

		ledger_path = Path(started["state_path"])
		original_ledger = ledger_path.read_text(encoding="utf-8")
		ledger = json.loads(original_ledger)
		ledger["status"] = "COMPLETE"
		write_json(ledger_path, ledger)
		tamper_result, tampered = runtime(project, "status")
		report.check("derived-run-status-tamper-refused", tamper_result.returncode != 0 and tampered.get("code") == "STATE_INVALID", str(tampered))
		write_text(ledger_path, original_ledger)

		print(f"Graph runtime tests: {report.passed} passed, {report.failed} failed")
		return 0 if report.failed == 0 else 1
	finally:
		shutil.rmtree(workspace, ignore_errors=True)


if __name__ == "__main__":
	raise SystemExit(main())
