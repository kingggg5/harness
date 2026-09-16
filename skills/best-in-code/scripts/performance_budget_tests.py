#!/usr/bin/env python3
"""Focused regression tests for the cross-language performance budget gate."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True

from pathlib import Path

import performance_budget


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


def load(path: Path) -> dict:
	return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
	report = Report()
	root = Path(__file__).resolve().parents[3]
	baseline = load(root / "examples" / "performance-baseline.json")
	current = load(root / "examples" / "performance-current.json")
	budget = load(root / "examples" / "performance-budget.json")
	passing = performance_budget.compare(baseline, current, budget)
	report.check(
		"comparable-correct-candidate-passes",
		passing["status"] == "PASS"
		and passing["comparability"]["status"] == "PASS"
		and passing["correctness"]["status"] == "PASS"
		and all(item["status"] == "PASS" for item in passing["metrics"])
		and passing["authority"] == "evidence_only",
		str(passing),
	)
	template_result = load(root / "skills" / "best-in-code" / "assets" / "templates" / "PERFORMANCE-RESULT.json")
	template_budget = load(root / "skills" / "best-in-code" / "assets" / "templates" / "PERFORMANCE-BUDGET.json")
	template_report = performance_budget.compare(template_result, template_result, template_budget)
	report.check(
		"zero-baseline-minimum-metric-is-comparable",
		template_report["status"] == "PASS",
		str(template_report),
	)

	p95_regression = json.loads(json.dumps(current))
	p95_regression["metrics"]["latency_p95_ms"] = 101
	p95_report = performance_budget.compare(baseline, p95_regression, budget)
	report.check(
		"absolute-latency-budget-fails",
		p95_report["status"] == "FAIL"
		and next(item for item in p95_report["metrics"] if item["name"] == "latency_p95_ms")["reason"] == "ABSOLUTE_LIMIT",
		str(p95_report),
	)

	changed_workload = json.loads(json.dumps(current))
	changed_workload["workload"]["dataset_digest"] = "sha256:" + "f" * 64
	workload_report = performance_budget.compare(baseline, changed_workload, budget)
	report.check(
		"changed-workload-fails-comparability",
		workload_report["status"] == "FAIL"
		and "CURRENT_WORKLOAD_MISMATCH" in workload_report["comparability"]["reasons"],
		str(workload_report),
	)

	changed_environment = json.loads(json.dumps(current))
	changed_environment["environment"]["runtime"] = "node-23.0"
	environment_report = performance_budget.compare(baseline, changed_environment, budget)
	report.check(
		"changed-environment-fails-when-policy-requires-match",
		environment_report["status"] == "FAIL"
		and "ENVIRONMENT_MISMATCH" in environment_report["comparability"]["reasons"],
		str(environment_report),
	)

	incorrect = json.loads(json.dumps(current))
	incorrect["correctness"]["status"] = "FAIL"
	incorrect_report = performance_budget.compare(baseline, incorrect, budget)
	report.check(
		"faster-but-incorrect-candidate-fails",
		incorrect_report["status"] == "FAIL"
		and "CURRENT_CORRECTNESS_FAILED" in incorrect_report["correctness"]["reasons"],
		str(incorrect_report),
	)

	missing_metric = json.loads(json.dumps(current))
	del missing_metric["metrics"]["throughput_per_second"]
	missing_report = performance_budget.compare(baseline, missing_metric, budget)
	report.check(
		"missing-budgeted-metric-fails",
		missing_report["status"] == "FAIL"
		and next(item for item in missing_report["metrics"] if item["name"] == "throughput_per_second")["reason"] == "MISSING_METRIC",
		str(missing_report),
	)

	regression_budget = json.loads(json.dumps(budget))
	regression_budget["metrics"][0]["limit"] = 200
	regression_current = json.loads(json.dumps(current))
	regression_current["metrics"]["latency_p95_ms"] = 121
	regression_report = performance_budget.compare(baseline, regression_current, regression_budget)
	report.check(
		"regression-limit-fails-even-under-absolute-limit",
		regression_report["status"] == "FAIL"
		and next(item for item in regression_report["metrics"] if item["name"] == "latency_p95_ms")["reason"] == "REGRESSION_LIMIT",
		str(regression_report),
	)

	invalid_budget = json.loads(json.dumps(budget))
	invalid_budget["metrics"][0]["name"] = "invented_metric"
	try:
		performance_budget.validate_budget(invalid_budget)
		invalid_rejected = False
	except performance_budget.PerformanceError:
		invalid_rejected = True
	report.check("unknown-metric-fails-closed", invalid_rejected, "unsupported metric rejected")

	with tempfile.TemporaryDirectory(prefix="harness-performance-budget-") as temporary:
		output_path = Path(temporary) / "report.json"
		cli = subprocess.run(
			[
				sys.executable,
				"-B",
				str(Path(__file__).resolve().parent / "performance_budget.py"),
				"--baseline", str(root / "examples" / "performance-baseline.json"),
				"--current", str(root / "examples" / "performance-current.json"),
				"--budget", str(root / "examples" / "performance-budget.json"),
				"--output", str(output_path),
				"--json",
			],
			cwd=str(root),
			capture_output=True,
			text=True,
			encoding="utf-8",
			check=False,
		)
		try:
			cli_report = json.loads(cli.stdout)
		except json.JSONDecodeError:
			cli_report = {}
		second = subprocess.run(
			[
				sys.executable,
				"-B",
				str(Path(__file__).resolve().parent / "performance_budget.py"),
				"--baseline", str(root / "examples" / "performance-baseline.json"),
				"--current", str(root / "examples" / "performance-current.json"),
				"--budget", str(root / "examples" / "performance-budget.json"),
				"--output", str(output_path),
			],
			cwd=str(root),
			capture_output=True,
			text=True,
			encoding="utf-8",
			check=False,
		)
		report.check(
			"cli-writes-once-and-refuses-overwrite",
			cli.returncode == 0
			and cli_report.get("status") == "PASS"
			and output_path.is_file()
			and second.returncode == 2,
			str({"first": cli_report, "second": second.stderr}),
		)
		launcher = subprocess.run(
			[
				"node",
				str(root / "bin" / "harness.js"),
				"perf-check",
				"--baseline", str(root / "examples" / "performance-baseline.json"),
				"--current", str(root / "examples" / "performance-current.json"),
				"--budget", str(root / "examples" / "performance-budget.json"),
				"--json",
			],
			cwd=str(root),
			capture_output=True,
			text=True,
			encoding="utf-8",
			check=False,
		)
		try:
			launcher_report = json.loads(launcher.stdout)
		except json.JSONDecodeError:
			launcher_report = {}
		report.check(
			"harness-launcher-routes-perf-check",
			launcher.returncode == 0 and launcher_report.get("status") == "PASS",
			str(launcher_report),
		)
		markdown = subprocess.run(
			[
				"node",
				str(root / "bin" / "harness.js"),
				"perf-check",
				"--baseline", str(root / "examples" / "performance-baseline.json"),
				"--current", str(root / "examples" / "performance-current.json"),
				"--budget", str(root / "examples" / "performance-budget.json"),
				"--format", "markdown",
			],
			cwd=str(root),
			capture_output=True,
			text=True,
			encoding="utf-8",
			check=False,
		)
		report.check(
			"perf-check-renders-reviewable-markdown",
			markdown.returncode == 0
			and "# Performance comparison: PASS" in markdown.stdout
			and "| latency_p95_ms |" in markdown.stdout
			and "| throughput_per_second |" in markdown.stdout,
			markdown.stdout,
		)
		validate_cli = subprocess.run(
			[
				sys.executable,
				"-B",
				str(Path(__file__).resolve().parent / "performance_budget.py"),
				"--validate",
				"--result", str(root / "examples" / "performance-current.json"),
				"--json",
			],
			cwd=str(root),
			capture_output=True,
			text=True,
			encoding="utf-8",
			check=False,
		)
		try:
			validate_report = json.loads(validate_cli.stdout)
		except json.JSONDecodeError:
			validate_report = {}
		validate_launcher = subprocess.run(
			[
				"node",
				str(root / "bin" / "harness.js"),
				"perf-validate",
				"--result", str(root / "examples" / "performance-current.json"),
				"--json",
			],
			cwd=str(root),
			capture_output=True,
			text=True,
			encoding="utf-8",
			check=False,
		)
		try:
			validate_launcher_report = json.loads(validate_launcher.stdout)
		except json.JSONDecodeError:
			validate_launcher_report = {}
		report.check(
			"perf-validate-cli-and-launcher-return-closed-evidence",
			validate_cli.returncode == 0
			and validate_report.get("status") == "VALID"
			and isinstance(validate_report.get("result_digest"), str)
			and validate_launcher.returncode == 0
			and validate_launcher_report.get("status") == "VALID",
			str({"cli": validate_report, "launcher": validate_launcher_report}),
		)

	print(json.dumps({"passed": report.passed, "failed": report.failed}, indent=2))
	return 0 if report.failed == 0 else 1


if __name__ == "__main__":
	raise SystemExit(main())
