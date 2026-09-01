#!/usr/bin/env python3
"""Regression tests for byte-exact pinned-runtime checks in Harness doctor."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True


SCRIPTS = Path(__file__).resolve().parent
FIXED_TIME = "2026-09-01T00:00:00Z"


def run(script: str, *args: str, expected: set[int] = {0}) -> dict[str, object]:
	environment = {**os.environ, "PYTHONIOENCODING": "utf-8", "HARNESS_FIXED_TIME": FIXED_TIME}
	result = subprocess.run(
		[sys.executable, str(SCRIPTS / script), *args],
		capture_output=True,
		text=True,
		encoding="utf-8",
		env=environment,
		timeout=45,
		check=False,
	)
	if result.returncode not in expected:
		raise AssertionError(f"{script} exited {result.returncode}: {result.stderr}\n{result.stdout}")
	try:
		return json.loads(result.stdout)
	except json.JSONDecodeError as exc:
		raise AssertionError(f"{script} returned invalid JSON: {result.stdout}") from exc


def runtime_check(report: dict[str, object]) -> dict[str, object]:
	checks = report.get("checks", [])
	if not isinstance(checks, list):
		raise AssertionError("doctor checks must be a list")
	for check in checks:
		if isinstance(check, dict) and check.get("check") == "runtime-pinned":
			return check
	raise AssertionError("doctor omitted runtime-pinned check")


def main() -> int:
	with tempfile.TemporaryDirectory(prefix="harness-doctor-runtime-") as temp:
		project = Path(temp) / "project"
		project.mkdir()
		run("init_project.py", "--project", str(project), "--models", "generic", "--json")
		healthy = run("memory_ops.py", "doctor", "--project", str(project), expected={0, 1})
		healthy_runtime = runtime_check(healthy)
		assert healthy_runtime.get("ok") is True, healthy_runtime
		assert healthy_runtime.get("digest_matches") is True, healthy_runtime
		assert isinstance(healthy_runtime.get("runtime_files"), int) and healthy_runtime["runtime_files"] > 10

		skill = project / ".harness" / "runtime" / "SKILL.md"
		skill.write_bytes(skill.read_bytes() + b"\n<!-- unauthorized runtime drift -->\n")
		drifted = run("memory_ops.py", "doctor", "--project", str(project), expected={0, 1})
		drifted_runtime = runtime_check(drifted)
		assert drifted_runtime.get("ok") is False, drifted_runtime
		assert drifted_runtime.get("digest_matches") is False, drifted_runtime
		assert drifted.get("verdict") == "DEGRADED", drifted
	print("Doctor runtime tests passed: exact pin accepted; byte drift rejected.")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
