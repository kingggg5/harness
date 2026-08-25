#!/usr/bin/env python3
"""Fail CI when the memory-eval result set loses expected coverage."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


EXPECTED_IDS = {f"M{number:02d}" for number in range(1, 42)}
EXTERNAL_MODEL_IDS = {"M05", "M06", "M28", "M31"}
VALID_STATUSES = {"PASS", "FAIL", "SKIP"}


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Enforce Harness memory-eval CI coverage")
	parser.add_argument("--results", required=True, help="JSON output from run_memory_evals.py")
	parser.add_argument("--os", required=True, choices=("Linux", "Windows"), help="GitHub runner operating system")
	return parser.parse_args()


def validate_report(data: Any, runner_os: str) -> list[str]:
	errors: list[str] = []
	if not isinstance(data, dict) or not isinstance(data.get("results"), list):
		return ["report must be an object with a results array"]
	results = data["results"]
	by_id: dict[str, str] = {}
	for index, result in enumerate(results):
		if not isinstance(result, dict):
			errors.append(f"results[{index}] must be an object")
			continue
		case_id = result.get("id")
		status = result.get("status")
		if not isinstance(case_id, str) or case_id not in EXPECTED_IDS:
			errors.append(f"results[{index}].id is unknown or invalid: {case_id!r}")
			continue
		if case_id in by_id:
			errors.append(f"duplicate result ID: {case_id}")
			continue
		if status not in VALID_STATUSES:
			errors.append(f"{case_id} has invalid status: {status!r}")
			continue
		by_id[case_id] = status
	missing = sorted(EXPECTED_IDS - set(by_id))
	if missing:
		errors.append(f"missing result IDs: {missing}")
	failed = sorted(case_id for case_id, status in by_id.items() if status == "FAIL")
	if failed:
		errors.append(f"failed cases: {failed}")
	allowed_skips = set(EXTERNAL_MODEL_IDS)
	if runner_os == "Windows":
		allowed_skips.add("M34")
	unexpected_skips = sorted(case_id for case_id, status in by_id.items() if status == "SKIP" and case_id not in allowed_skips)
	if unexpected_skips:
		errors.append(f"unexpected skipped cases on {runner_os}: {unexpected_skips}")
	return errors


def main() -> int:
	args = parse_args()
	try:
		data = json.loads(Path(args.results).read_text(encoding="utf-8"))
	except (OSError, UnicodeDecodeError, json.JSONDecodeError, MemoryError) as exc:
		print(f"Memory-eval policy failed: could not read report: {exc}", file=sys.stderr)
		return 1
	errors = validate_report(data, args.os)
	if errors:
		print("Memory-eval policy failed:", file=sys.stderr)
		for error in errors:
			print(f"- {error}", file=sys.stderr)
		return 1
	counts = {status: sum(1 for result in data["results"] if result["status"] == status) for status in sorted(VALID_STATUSES)}
	print(f"Memory-eval policy passed on {args.os}: {counts}")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
