#!/usr/bin/env python3
"""Integration tests for the optional Harness loop supervisor ledger."""

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
RUNTIME = SCRIPTS / "loop_runtime.py"
INIT = SCRIPTS / "init_project.py"
TEMPLATE = ROOT / "skills" / "best-in-code" / "assets" / "templates" / "LOOP-CONTRACT.json"
PROJECT_ID = "project-22222222-2222-4222-8222-222222222222"
RUN_ID = "RUN-loop-runtime-test"


class Report:
	def __init__(self) -> None:
		self.passed = 0
		self.failed = 0

	def check(self, name: str, condition: bool, detail: str) -> None:
		detail = re.sub(r"ltok_[0-9a-f]{64}", "<redacted-claim-token>", detail)
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
	return subprocess.run(
		command, cwd=str(cwd), env=merged, capture_output=True, text=True,
		encoding="utf-8", errors="replace", timeout=120, check=False,
	)


def git(project: Path, *arguments: str) -> str:
	result = process(["git", *arguments], project)
	if result.returncode != 0:
		raise RuntimeError(result.stderr or result.stdout)
	return result.stdout.strip()


def runtime(project: Path, command: str, *arguments: str, env: dict[str, str] | None = None) -> tuple[subprocess.CompletedProcess, dict]:
	base = [
		sys.executable, str(RUNTIME), command,
		"--project", str(project), "--contract", ".harness/LOOP-CONTRACT.json",
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


def make_fixture(
	root: Path, name: str, *, scheduled: bool = False, writing: bool = False,
	max_iterations: int = 6, max_tokens: int = 1000, max_external_calls: int = 10,
) -> tuple[Path, str]:
	project = root / name
	project.mkdir()
	git(project, "init", "-b", "main")
	git(project, "config", "user.email", "harness-test@example.invalid")
	git(project, "config", "user.name", "Harness Test")
	write_text(project / "src" / "base.txt", "baseline\n")
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
	contract = json.loads(TEMPLATE.read_text(encoding="utf-8"))
	contract.update({
		"loop_id": "runtime-loop", "project_id": PROJECT_ID, "run_id": RUN_ID,
		"level": "scheduled" if scheduled else "goal",
	})
	contract["trigger"].update({
		"type": "schedule" if scheduled else "human",
		"spec": "host schedule delivery" if scheduled else "human starts the bounded goal",
		"dedupe_key": f"runtime-loop:{RUN_ID}",
		"overlap_policy": "queue-one" if scheduled else "reject",
		"max_runs": 3 if scheduled else 1,
	})
	contract["verifiers"] = [{
		"id": "acceptance", "kind": "deterministic", "command_id": "acceptance",
		"success": "The trusted acceptance receipt reports success.",
		"evidence_path": ".harness/evidence/loop-acceptance.json",
	}]
	contract["budgets"].update({
		"max_iterations": max_iterations, "max_elapsed_seconds": 120,
		"max_iteration_seconds": 1, "max_tokens": max_tokens,
		"max_cost_microusd": 1000, "max_external_calls": max_external_calls,
		"max_consecutive_failures": min(3, max_iterations),
		"no_progress_cycles": min(2, max_iterations), "max_parallel": 1,
	})
	contract["control"].update({
		"execution_strategy": "single-owner", "graph_id": "", "write_scope": ["src"] if writing else [],
		"rollback_revision": base if writing else "",
	})
	write_json(project / ".harness" / "LOOP-CONTRACT.json", contract)
	write_json(project / ".harness" / "evidence" / "loop-acceptance.json", {"ok": True, "round": 0})
	write_json(project / ".harness" / "evidence" / "loop-best.json", {"score": 0})
	return project, base


def claim(project: Path, revision: int, worker: str = "Loop Worker") -> tuple[subprocess.CompletedProcess, dict]:
	return runtime(project, "claim", "--worker", worker, "--expected-revision", str(revision))


def finish(
	project: Path, token: str, revision: int, outcome: str, *arguments: str,
) -> tuple[subprocess.CompletedProcess, dict]:
	return runtime(
		project, "finish", "--outcome", outcome, "--expected-revision", str(revision),
		*arguments, env={"HARNESS_LOOP_CLAIM_TOKEN": token},
	)


def main() -> int:
	report = Report()
	workspace = Path(tempfile.mkdtemp(prefix="harness-loop-runtime-"))
	try:
		project, _ = make_fixture(workspace, "goal")
		started_result, started = runtime(project, "start")
		report.check("goal-runtime-start", started_result.returncode == 0 and started.get("revision") == 0 and started.get("status") == "ACTIVE", str(started))
		duplicate_result, duplicate = runtime(project, "start")
		report.check("duplicate-runtime-start-refused", duplicate_result.returncode != 0 and duplicate.get("code") == "TARGET_EXISTS", str(duplicate))

		claim_command = [
			sys.executable, str(RUNTIME), "claim", "--project", str(project),
			"--contract", ".harness/LOOP-CONTRACT.json", "--worker", "Concurrent Worker",
			"--expected-revision", "0",
		]
		claimers = [
			subprocess.Popen(
				claim_command, cwd=str(project), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
				text=True, encoding="utf-8", errors="replace",
			) for _ in range(2)
		]
		claim_payloads = [json.loads(process_item.communicate(timeout=120)[0]) for process_item in claimers]
		winners = [payload for payload in claim_payloads if payload.get("ok")]
		loser_codes = {payload.get("code") for payload in claim_payloads if not payload.get("ok")}
		report.check("concurrent-iteration-cas", len(winners) == 1 and loser_codes.issubset({"ITERATION_RUNNING", "REVISION_CONFLICT"}), str(claim_payloads))
		first_claim = winners[0]
		ledger_text = Path(started["state_path"]).read_text(encoding="utf-8")
		report.check("raw-loop-token-not-persisted", first_claim["claim_token"] not in ledger_text, "ledger stores only a digest")

		(project / ".harness" / "evidence" / "loop-acceptance.json").unlink()
		bad_token_result, bad_token = finish(
			project, "ltok_" + "0" * 64, 1, "improved", "--verifier", "acceptance",
		)
		report.check("claim-checked-before-evidence-read", bad_token_result.returncode != 0 and bad_token.get("code") == "CLAIM_MISMATCH", str(bad_token))
		write_json(project / ".harness" / "evidence" / "loop-acceptance.json", {"ok": True, "round": 1})
		missing_best_result, missing_best = finish(
			project, first_claim["claim_token"], 1, "pass", "--verifier", "acceptance",
		)
		report.check("pass-requires-best-artifact", missing_best_result.returncode != 0 and missing_best.get("code") == "BEST_REQUIRED", str(missing_best))
		missing_verifier_result, missing_verifier = finish(
			project, first_claim["claim_token"], 1, "pass", "--accept-best",
		)
		report.check("pass-requires-all-verifiers", missing_verifier_result.returncode != 0 and missing_verifier.get("code") == "VERIFIER_INCOMPLETE", str(missing_verifier))
		_, improved = finish(
			project, first_claim["claim_token"], 1, "improved", "--verifier", "acceptance",
			"--accept-best", "--tokens", "3",
		)
		report.check("iteration-receipts-and-usage-recorded", improved.get("revision") == 2 and improved.get("status") == "ACTIVE" and improved.get("usage", {}).get("tokens") == 3, str(improved))

		_, paused = runtime(project, "pause", "--note", "Human review", "--expected-revision", "2")
		paused_claim_result, paused_claim = claim(project, 3)
		report.check("human-pause-blocks-new-claim", paused.get("status") == "PAUSED" and paused_claim_result.returncode != 0 and paused_claim.get("code") == "LOOP_NOT_ACTIVE", str(paused_claim))
		_, resumed = runtime(project, "resume", "--expected-revision", "3")
		_, stale_claim = claim(project, 4)
		time.sleep(1.1)
		_, recovered = runtime(
			project, "recover", "--claim-id", stale_claim["claim_id"], "--action", "continue",
			"--note", "Worker heartbeat expired", "--expected-revision", "5",
		)
		report.check("timed-out-iteration-recovered", resumed.get("status") == "ACTIVE" and recovered.get("revision") == 6 and recovered.get("status") == "ACTIVE", str(recovered))

		_, no_progress_claim_one = claim(project, 6)
		_, no_progress_one = finish(project, no_progress_claim_one["claim_token"], 7, "no-progress")
		_, no_progress_claim_two = claim(project, 8)
		_, no_progress_two = finish(project, no_progress_claim_two["claim_token"], 9, "no-progress")
		report.check("no-progress-stop-is-enforced", no_progress_one.get("status") == "ACTIVE" and no_progress_two.get("status") == "NO_PROGRESS", str(no_progress_two))
		contract_path = project / ".harness" / "LOOP-CONTRACT.json"
		changed_contract = json.loads(contract_path.read_text(encoding="utf-8"))
		changed_contract["objective"]["outcome"] += " Changed after start."
		write_json(contract_path, changed_contract)
		contract_change_result, contract_change = runtime(project, "status")
		report.check("active-contract-change-fails-closed", contract_change_result.returncode != 0 and contract_change.get("code") == "STATE_INVALID", str(contract_change))

		scheduled, _ = make_fixture(workspace, "scheduled", scheduled=True, max_iterations=2)
		_, schedule_started = runtime(scheduled, "start", "--delivery-id", "delivery-1")
		_, queued = runtime(scheduled, "trigger", "--delivery-id", "delivery-2", "--expected-revision", "0")
		duplicate_delivery_result, duplicate_delivery = runtime(scheduled, "trigger", "--delivery-id", "delivery-2", "--expected-revision", "1")
		report.check("scheduled-overlap-queues-once", schedule_started.get("run_count") == 1 and queued.get("queued_trigger") is True and duplicate_delivery_result.returncode != 0 and duplicate_delivery.get("code") == "TRIGGER_DUPLICATE", str(duplicate_delivery))
		_, scheduled_claim_one = claim(scheduled, 1)
		write_json(scheduled / ".harness" / "evidence" / "loop-acceptance.json", {"ok": True, "round": 1})
		_, scheduled_pass_one = finish(
			scheduled, scheduled_claim_one["claim_token"], 2, "pass", "--verifier", "acceptance", "--accept-best",
		)
		report.check("queued-run-starts-after-pass", scheduled_pass_one.get("revision") == 3 and scheduled_pass_one.get("status") == "ACTIVE" and scheduled_pass_one.get("run_count") == 2, str(scheduled_pass_one))
		_, scheduled_claim_two = claim(scheduled, 3)
		write_json(scheduled / ".harness" / "evidence" / "loop-acceptance.json", {"ok": True, "round": 2})
		_, scheduled_pass_two = finish(
			scheduled, scheduled_claim_two["claim_token"], 4, "pass", "--verifier", "acceptance", "--accept-best",
		)
		verified_result, verified = runtime(scheduled, "status", "--verify-evidence")
		report.check("latest-receipt-survives-evidence-rotation", scheduled_pass_two.get("status") == "WAITING_TRIGGER" and verified_result.returncode == 0 and verified.get("evidence_verified") is True, str(verified))
		_, trigger_three = runtime(scheduled, "trigger", "--delivery-id", "delivery-3", "--expected-revision", "5")
		_, scheduled_claim_three = claim(scheduled, 6)
		write_json(scheduled / ".harness" / "evidence" / "loop-acceptance.json", {"ok": True, "round": 3})
		_, scheduled_pass_three = finish(
			scheduled, scheduled_claim_three["claim_token"], 7, "pass", "--verifier", "acceptance", "--accept-best",
		)
		report.check("scheduled-loop-terminates-at-run-budget", trigger_three.get("run_count") == 3 and scheduled_pass_three.get("status") == "PASS_WITH_EVIDENCE" and scheduled_pass_three.get("completed_runs") == 3, str(scheduled_pass_three))

		budget, _ = make_fixture(workspace, "budget", max_external_calls=0)
		_, budget_started = runtime(budget, "start")
		_, budget_claim = claim(budget, 0)
		_, budget_done = finish(
			budget, budget_claim["claim_token"], 1, "improved", "--accept-best", "--external-calls", "1",
		)
		report.check("zero-external-call-budget-is-a-ceiling", budget_started.get("status") == "ACTIVE" and budget_done.get("status") == "BUDGET_EXHAUSTED" and budget_done.get("budget_stop_reason") == "max_external_calls", str(budget_done))

		writing, write_base = make_fixture(workspace, "writing", writing=True)
		_, writing_started = runtime(writing, "start")
		_, writing_claim = claim(writing, 0)
		bad_branch = "scope-violation"
		bad_worktree = workspace / "bad-worktree"
		git(writing, "worktree", "add", "-b", bad_branch, str(bad_worktree), write_base)
		write_text(bad_worktree / "outside.txt", "outside scope\n")
		git(bad_worktree, "add", "outside.txt")
		git(bad_worktree, "commit", "-m", "outside scope")
		bad_revision = git(bad_worktree, "rev-parse", "HEAD")
		bad_scope_result, bad_scope = finish(
			writing, writing_claim["claim_token"], 1, "improved", "--result-revision", bad_revision,
		)
		report.check("accepted-result-respects-write-scope", writing_started.get("source_revision") == write_base and bad_scope_result.returncode != 0 and bad_scope.get("code") == "WRITE_SCOPE_VIOLATION", str(bad_scope))
		write_text(writing / "src" / "accepted.txt", "accepted\n")
		git(writing, "add", "src/accepted.txt")
		git(writing, "commit", "-m", "accepted scoped result")
		accepted_revision = git(writing, "rev-parse", "HEAD")
		_, accepted = finish(
			writing, writing_claim["claim_token"], 1, "improved", "--result-revision", accepted_revision,
			"--accept-best",
		)
		report.check("accepted-commit-becomes-next-baseline", accepted.get("source_revision") == accepted_revision and accepted.get("best_source_revision") == accepted_revision, str(accepted))
		leaked_path = writing / "src" / "uncommitted-between-iterations.txt"
		write_text(leaked_path, "must not leak\n")
		dirty_claim_result, dirty_claim = claim(writing, 2)
		report.check("dirty-source-cannot-seed-next-iteration", dirty_claim_result.returncode != 0 and dirty_claim.get("code") == "DIRTY_BASELINE", str(dirty_claim))
		leaked_path.unlink()
		_, next_claim = claim(writing, 2)
		report.check("next-iteration-binds-accepted-commit", next_claim.get("source_revision") == accepted_revision, str(next_claim))

		dirty, _ = make_fixture(workspace, "dirty", writing=True)
		write_text(dirty / "src" / "uncommitted.txt", "dirty\n")
		dirty_result, dirty_start = runtime(dirty, "start")
		report.check("dirty-writing-baseline-refused", dirty_result.returncode != 0 and dirty_start.get("code") == "DIRTY_BASELINE", str(dirty_start))

		state_path = Path(budget_done["state_path"])
		tampered = json.loads(state_path.read_text(encoding="utf-8"))
		tampered["events"][-1]["note"] = "tampered"
		write_json(state_path, tampered)
		tamper_result, tamper_status = runtime(budget, "status")
		report.check("event-chain-tampering-detected", tamper_result.returncode != 0 and tamper_status.get("code") == "STATE_INVALID", str(tamper_status))
	finally:
		for project in workspace.iterdir() if workspace.exists() else []:
			if project.is_dir() and (project / ".git").exists():
				process(["git", "worktree", "prune"], project)
		shutil.rmtree(workspace, ignore_errors=True)

	print(f"Loop runtime tests: {report.passed} passed, {report.failed} failed")
	return 1 if report.failed else 0


if __name__ == "__main__":
	raise SystemExit(main())
