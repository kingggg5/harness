#!/usr/bin/env python3
"""Regression tests for the GitHub Actions memory-eval coverage policy."""

from __future__ import annotations

import copy
import sys

sys.dont_write_bytecode = True

from check_eval_results import EXPECTED_IDS, EXTERNAL_MODEL_IDS, validate_report


def report_for(runner_os: str) -> dict:
	allowed_skips = set(EXTERNAL_MODEL_IDS)
	if runner_os == "Windows":
		allowed_skips.add("M34")
	return {
		"results": [
			{"id": case_id, "status": "SKIP" if case_id in allowed_skips else "PASS"}
			for case_id in sorted(EXPECTED_IDS)
		]
	}


def expect(label: str, report: dict, runner_os: str, fragment: str | None = None) -> bool:
	errors = validate_report(report, runner_os)
	passed = not errors if fragment is None else any(fragment in error for error in errors)
	print(f"[{'PASS' if passed else 'FAIL'}] {label}: {'valid' if not errors else ' | '.join(errors)}")
	return passed


def main() -> int:
	windows = report_for("Windows")
	linux = report_for("Linux")
	cases: list[bool] = [
		expect("expected-windows-coverage", windows, "Windows"),
		expect("expected-linux-coverage", linux, "Linux"),
	]

	failed_external = copy.deepcopy(windows)
	next(result for result in failed_external["results"] if result["id"] == "M05")["status"] = "FAIL"
	cases.append(expect("external-fail-is-not-tolerated", failed_external, "Windows", "failed cases"))

	unexpected_skip = copy.deepcopy(windows)
	next(result for result in unexpected_skip["results"] if result["id"] == "M01")["status"] = "SKIP"
	cases.append(expect("unexpected-skip-is-not-tolerated", unexpected_skip, "Windows", "unexpected skipped"))

	linux_windows_skip = copy.deepcopy(linux)
	next(result for result in linux_windows_skip["results"] if result["id"] == "M34")["status"] = "SKIP"
	cases.append(expect("windows-only-skip-is-rejected-on-linux", linux_windows_skip, "Linux", "unexpected skipped"))

	missing = copy.deepcopy(windows)
	missing["results"] = missing["results"][:-1]
	cases.append(expect("missing-case-is-rejected", missing, "Windows", "missing result IDs"))

	passed = sum(cases)
	print(f"CI policy tests: {passed}/{len(cases)} passed")
	return 0 if all(cases) else 1


if __name__ == "__main__":
	raise SystemExit(main())
