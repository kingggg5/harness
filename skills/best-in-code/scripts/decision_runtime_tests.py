#!/usr/bin/env python3
"""Focused tests for the dependency-free Harness decision runtime."""

from __future__ import annotations

import json
import subprocess
import sys

sys.dont_write_bytecode = True

from pathlib import Path

import decision_runtime


class Report:
	def __init__(self) -> None:
		self.passed = 0
		self.failed = 0

	def check(self, name: str, condition: bool, detail: str) -> None:
		if condition:
			self.passed += 1
			print(f"[PASS] {name}: {detail}")
		else:
			self.failed += 1
			print(f"[FAIL] {name}: {detail}")


def main() -> int:
	report = Report()
	root = Path(__file__).resolve().parent.parent
	suite_path = root / "assets" / "evals" / "DECISION-SUITE.json"
	suite = decision_runtime._load_json(suite_path, label="decision suite")
	validated = decision_runtime._validate_suite(suite)
	report.check("decision-suite-validates", len(validated["cases"]) == 5, str(validated["suite_id"]))

	questions = suite["questions"]
	quick = decision_runtime.decide({"task": "Fix a spelling typo in one button label."}, questions)
	quick_route = quick["decisions"]["route"]
	report.check(
		"quick-task-routes-without-execution-authority",
		quick_route["value"] == "quick"
		and quick["recommendation_only"] is True
		and quick["policy_authority"] is False
		and quick["policy_recommendation"]["status"] == "ADVISORY"
		and quick["policy_recommendation"]["effective_next_step"] == "run_quick_policy"
		and abs(sum(quick_route["probabilities"].values()) - 1) < 0.00001,
		str(quick),
	)
	production = decision_runtime.decide({"task": "Migrate authentication and tenant data in production."}, questions)
	report.check(
		"risky-task-recommends-human-review",
		production["decisions"]["route"]["value"] == "full"
		and production["decisions"]["needs_human"]["value"] is True
		and production["decisions"]["risk"]["value"] == 0.4,
		str(production),
	)
	try:
		decision_runtime.validate_questions({"schema_version": 1, "questions": [{"id": "route", "type": "choice", "options": ["quick", "quick"]}]})
		malformed_rejected = False
	except decision_runtime.DecisionError:
		malformed_rejected = True
	report.check("malformed-question-schema-fails-closed", malformed_rejected, "duplicate choice rejected")
	security_review = decision_runtime.decide({"task": "Research a security vulnerability and review the affected dependency."}, questions)
	report.check(
		"security-risk-cannot-bypass-human-floor",
		security_review["policy_recommendation"]["status"] == "HUMAN_REQUIRED"
		and "SECURITY_THRESHOLD" in security_review["policy_recommendation"]["reasons"],
		str(security_review["policy_recommendation"]),
	)
	try:
		decision_runtime.decide({"task": "x" * (decision_runtime.MAX_INPUT_BYTES + 1)}, questions)
		oversized_rejected = False
	except decision_runtime.DecisionError:
		oversized_rejected = True
	report.check("oversized-state-fails-closed", oversized_rejected, "bounded input rejected")

	evaluation = decision_runtime.evaluate_suite(suite, trials=2)
	metrics = evaluation["metrics"]
	report.check(
		"deterministic-benchmark-passes",
		evaluation["summary"]["status"] == "PASS"
		and evaluation["summary"]["total"] == 10
		and evaluation["summary"]["failed"] == 0
		and metrics["accuracy"] == 1
		and all(key in metrics for key in ("macro_f1", "brier_score", "ece", "latency_ms", "decisions_per_sec", "rss_mb")),
		str({"summary": evaluation["summary"], "metrics": metrics}),
	)
	representative_path = root / "assets" / "evals" / "DECISION-REPRESENTATIVE-SUITE.json"
	representative_suite = decision_runtime._load_json(representative_path, label="representative decision suite")
	representative_evaluation = decision_runtime.evaluate_suite(representative_suite, trials=2)
	representative_metrics = representative_evaluation["metrics"]
	report.check(
		"representative-decision-baseline-is-measurable",
		representative_evaluation["summary"]["total"] == 40
		and representative_evaluation["summary"]["status"] == "PASS"
		and representative_metrics["accuracy"] >= 0.95
		and representative_metrics["macro_f1"] >= 0.95,
		str({"summary": representative_evaluation["summary"], "metrics": representative_metrics}),
	)

	cli = subprocess.run(
		[
			sys.executable,
			"-B",
			str(Path(__file__).resolve().parent / "decision_runtime.py"),
			"eval",
			"--suite",
			str(suite_path),
			"--trials",
			"1",
			"--json",
		],
		cwd=str(root),
		capture_output=True,
		text=True,
		encoding="utf-8",
		check=False,
	)
	try:
		cli_payload = json.loads(cli.stdout)
	except json.JSONDecodeError:
		cli_payload = {}
	report.check(
		"decision-cli-emits-machine-readable-report",
		cli.returncode == 0 and cli_payload.get("summary", {}).get("status") == "PASS",
		str(cli_payload),
	)
	print(json.dumps({"passed": report.passed, "failed": report.failed}, indent=2))
	return 0 if report.failed == 0 else 1


if __name__ == "__main__":
	raise SystemExit(main())
