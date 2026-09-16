#!/usr/bin/env python3
"""Compare bounded, cross-language performance evidence without executing code.

Each project owns its benchmark command and emits a closed JSON result. This
tool verifies that baseline and candidate use the same declared workload, then
applies deterministic correctness and metric budgets. It never runs a command,
profiles a process, or treats a faster result as authorization for an effect.
"""

from __future__ import annotations

import argparse

# Keep this before local imports so direct test execution cannot create .pyc.
import sys

sys.dont_write_bytecode = True

import hashlib
import json
import math
import os
import re
import stat
import tempfile
from pathlib import Path
from typing import Any

from bounded_json import load_bounded_json, unique_object


SCHEMA_VERSION = 1
MAX_FILE_BYTES = 256 * 1024
MAX_OUTPUT_BYTES = 2 * 1024 * 1024
MAX_TEXT_BYTES = 512
MAX_METRICS = 16
MAX_SAMPLES = 10_000
ID_PATTERN = re.compile(r"^[a-z][a-z0-9._-]{0,127}$")
DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
MODES = {"cold", "warm"}
METRIC_DIRECTIONS = {
	"latency_p50_ms": "max",
	"latency_p95_ms": "max",
	"latency_p99_ms": "max",
	"throughput_per_second": "min",
	"rss_bytes": "max",
	"heap_bytes": "max",
	"cpu_seconds": "max",
	"read_bytes": "max",
	"write_bytes": "max",
	"error_rate": "max",
	"allocations": "max",
}
WORKLOAD_FIELDS = {"id", "dataset_digest", "command_digest", "distribution_digest", "mode", "sample_count"}
ENVIRONMENT_FIELDS = {"runtime", "target", "host_class"}
CORRECTNESS_FIELDS = {"status", "evidence_digest"}
RESULT_FIELDS = {"schema_version", "result_id", "workload", "environment", "correctness", "metrics"}
COMPARISON_FIELDS = {"require_same_environment"}
BUDGET_METRIC_FIELDS = {"name", "limit", "max_regression_ppm"}
BUDGET_FIELDS = {"schema_version", "budget_id", "workload", "comparison", "metrics"}


class PerformanceError(ValueError):
	"""Raised for malformed performance evidence or a malformed budget."""


def _canonical_json(value: Any) -> bytes:
	try:
		return json.dumps(
			value,
			ensure_ascii=False,
			sort_keys=True,
			separators=(",", ":"),
			allow_nan=False,
		).encode("utf-8")
	except (TypeError, ValueError, RecursionError, MemoryError) as exc:
		raise PerformanceError(f"value cannot be encoded as JSON: {exc}") from exc


def _digest(value: Any) -> str:
	return "sha256:" + hashlib.sha256(_canonical_json(value)).hexdigest()


def _closed_object(value: Any, fields: set[str], label: str) -> dict[str, Any]:
	if not isinstance(value, dict):
		raise PerformanceError(f"{label} must be an object")
	missing = fields - set(value)
	unknown = set(value) - fields
	if missing:
		raise PerformanceError(f"{label} is missing fields: {sorted(missing)}")
	if unknown:
		raise PerformanceError(f"{label} has unknown fields: {sorted(unknown)}")
	return value


def _safe_id(value: Any, label: str) -> str:
	if not isinstance(value, str) or not ID_PATTERN.fullmatch(value):
		raise PerformanceError(f"{label} must be a bounded identifier")
	return value


def _safe_text(value: Any, label: str) -> str:
	if not isinstance(value, str) or not value.strip() or "\x00" in value or len(value.encode("utf-8")) > MAX_TEXT_BYTES:
		raise PerformanceError(f"{label} must be non-empty text of at most {MAX_TEXT_BYTES} bytes")
	return value


def _safe_digest(value: Any, label: str) -> str:
	if not isinstance(value, str) or DIGEST_PATTERN.fullmatch(value) is None:
		raise PerformanceError(f"{label} must be a sha256 digest")
	return value


def _safe_number(value: Any, label: str, *, minimum: float = 0.0, maximum: float = 10**18) -> float:
	if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
		raise PerformanceError(f"{label} must be a finite number")
	result = float(value)
	if not minimum <= result <= maximum:
		raise PerformanceError(f"{label} must be from {minimum} to {maximum}")
	return result


def _safe_integer(value: Any, label: str, *, minimum: int, maximum: int) -> int:
	if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
		raise PerformanceError(f"{label} must be an integer from {minimum} to {maximum}")
	return value


def validate_workload(value: Any, label: str = "workload") -> dict[str, Any]:
	workload = _closed_object(value, WORKLOAD_FIELDS, label)
	validated = {
		"id": _safe_id(workload["id"], f"{label}.id"),
		"dataset_digest": _safe_digest(workload["dataset_digest"], f"{label}.dataset_digest"),
		"command_digest": _safe_digest(workload["command_digest"], f"{label}.command_digest"),
		"distribution_digest": _safe_digest(workload["distribution_digest"], f"{label}.distribution_digest"),
		"mode": workload["mode"],
		"sample_count": _safe_integer(workload["sample_count"], f"{label}.sample_count", minimum=1, maximum=MAX_SAMPLES),
	}
	if validated["mode"] not in MODES:
		raise PerformanceError(f"{label}.mode must be one of {sorted(MODES)}")
	return validated


def validate_environment(value: Any, label: str = "environment") -> dict[str, str]:
	environment = _closed_object(value, ENVIRONMENT_FIELDS, label)
	return {field: _safe_text(environment[field], f"{label}.{field}") for field in sorted(ENVIRONMENT_FIELDS)}


def validate_result(value: Any, label: str = "performance result") -> dict[str, Any]:
	result = _closed_object(value, RESULT_FIELDS, label)
	if result["schema_version"] != SCHEMA_VERSION:
		raise PerformanceError(f"{label}.schema_version must be {SCHEMA_VERSION}")
	correctness = _closed_object(result["correctness"], CORRECTNESS_FIELDS, f"{label}.correctness")
	if correctness["status"] not in {"PASS", "FAIL"}:
		raise PerformanceError(f"{label}.correctness.status must be PASS or FAIL")
	metrics = result["metrics"]
	if not isinstance(metrics, dict) or not 1 <= len(metrics) <= MAX_METRICS:
		raise PerformanceError(f"{label}.metrics must contain 1 to {MAX_METRICS} values")
	unknown_metrics = set(metrics) - set(METRIC_DIRECTIONS)
	if unknown_metrics:
		raise PerformanceError(f"{label}.metrics has unsupported names: {sorted(unknown_metrics)}")
	validated_metrics = {name: _safe_number(number, f"{label}.metrics.{name}") for name, number in metrics.items()}
	if "error_rate" in validated_metrics and validated_metrics["error_rate"] > 1:
		raise PerformanceError(f"{label}.metrics.error_rate must be from 0 to 1")
	return {
		"schema_version": SCHEMA_VERSION,
		"result_id": _safe_id(result["result_id"], f"{label}.result_id"),
		"workload": validate_workload(result["workload"], f"{label}.workload"),
		"environment": validate_environment(result["environment"], f"{label}.environment"),
		"correctness": {
			"status": correctness["status"],
			"evidence_digest": _safe_digest(correctness["evidence_digest"], f"{label}.correctness.evidence_digest"),
		},
		"metrics": validated_metrics,
	}


def validate_budget(value: Any, label: str = "performance budget") -> dict[str, Any]:
	budget = _closed_object(value, BUDGET_FIELDS, label)
	if budget["schema_version"] != SCHEMA_VERSION:
		raise PerformanceError(f"{label}.schema_version must be {SCHEMA_VERSION}")
	comparison = _closed_object(budget["comparison"], COMPARISON_FIELDS, f"{label}.comparison")
	if not isinstance(comparison["require_same_environment"], bool):
		raise PerformanceError(f"{label}.comparison.require_same_environment must be boolean")
	metrics = budget["metrics"]
	if not isinstance(metrics, list) or not 1 <= len(metrics) <= MAX_METRICS:
		raise PerformanceError(f"{label}.metrics must contain 1 to {MAX_METRICS} items")
	seen: set[str] = set()
	validated_metrics: list[dict[str, Any]] = []
	for index, raw_metric in enumerate(metrics):
		metric = _closed_object(raw_metric, BUDGET_METRIC_FIELDS, f"{label}.metrics[{index}]")
		name = metric["name"]
		if name not in METRIC_DIRECTIONS:
			raise PerformanceError(f"{label}.metrics[{index}].name is unsupported")
		if name in seen:
			raise PerformanceError(f"{label}.metrics contains duplicate name {name!r}")
		seen.add(name)
		validated_metrics.append({
			"name": name,
			"limit": _safe_number(metric["limit"], f"{label}.metrics[{index}].limit"),
			"max_regression_ppm": _safe_integer(metric["max_regression_ppm"], f"{label}.metrics[{index}].max_regression_ppm", minimum=0, maximum=1_000_000),
			"direction": METRIC_DIRECTIONS[name],
		})
	return {
		"schema_version": SCHEMA_VERSION,
		"budget_id": _safe_id(budget["budget_id"], f"{label}.budget_id"),
		"workload": validate_workload(budget["workload"], f"{label}.workload"),
		"comparison": {"require_same_environment": comparison["require_same_environment"]},
		"metrics": validated_metrics,
	}


def _load_json(path: Path, label: str) -> Any:
	value, errors = load_bounded_json(path, max_bytes=MAX_FILE_BYTES, label=label)
	if errors:
		raise PerformanceError(" | ".join(errors))
	return value


def _metric_result(metric: dict[str, Any], baseline: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
	name = metric["name"]
	if name not in baseline["metrics"] or name not in current["metrics"]:
		return {
			"name": name,
			"direction": metric["direction"],
			"baseline": baseline["metrics"].get(name),
			"current": current["metrics"].get(name),
			"limit": metric["limit"],
			"max_regression_ppm": metric["max_regression_ppm"],
			"regression_ppm": None,
			"status": "FAIL",
			"reason": "MISSING_METRIC",
		}
	baseline_value = baseline["metrics"][name]
	current_value = current["metrics"][name]
	direction = metric["direction"]
	if direction == "max":
		absolute_pass = current_value <= metric["limit"]
		regression_ppm = ((current_value / baseline_value) - 1) * 1_000_000 if baseline_value > 0 else None
		regression_pass = baseline_value == 0 or current_value <= baseline_value * (1 + metric["max_regression_ppm"] / 1_000_000)
	else:
		absolute_pass = current_value >= metric["limit"]
		regression_ppm = ((baseline_value / current_value) - 1) * 1_000_000 if current_value > 0 else None
		regression_pass = baseline_value == 0 or current_value >= baseline_value * (1 - metric["max_regression_ppm"] / 1_000_000)
	if absolute_pass and regression_pass:
		status = "PASS"
		reason = ""
	elif not absolute_pass:
		status = "FAIL"
		reason = "ABSOLUTE_LIMIT"
	else:
		status = "FAIL"
		reason = "REGRESSION_LIMIT"
	return {
		"name": name,
		"direction": direction,
		"baseline": baseline_value,
		"current": current_value,
		"limit": metric["limit"],
		"max_regression_ppm": metric["max_regression_ppm"],
		"regression_ppm": round(regression_ppm, 3) if regression_ppm is not None else None,
		"status": status,
		"reason": reason,
	}


def compare(baseline: dict[str, Any], current: dict[str, Any], budget: dict[str, Any]) -> dict[str, Any]:
	baseline = validate_result(baseline, "baseline")
	current = validate_result(current, "current")
	budget = validate_budget(budget, "budget")
	comparability_reasons: list[str] = []
	if baseline["workload"] != budget["workload"]:
		comparability_reasons.append("BASELINE_WORKLOAD_MISMATCH")
	if current["workload"] != budget["workload"]:
		comparability_reasons.append("CURRENT_WORKLOAD_MISMATCH")
	if budget["comparison"]["require_same_environment"] and baseline["environment"] != current["environment"]:
		comparability_reasons.append("ENVIRONMENT_MISMATCH")
	correctness_reasons = []
	if baseline["correctness"]["status"] != "PASS":
		correctness_reasons.append("BASELINE_CORRECTNESS_FAILED")
	if current["correctness"]["status"] != "PASS":
		correctness_reasons.append("CURRENT_CORRECTNESS_FAILED")
	metrics = [_metric_result(metric, baseline, current) for metric in budget["metrics"]]
	status = "PASS" if not comparability_reasons and not correctness_reasons and all(metric["status"] == "PASS" for metric in metrics) else "FAIL"
	return {
		"schema_version": SCHEMA_VERSION,
		"budget_id": budget["budget_id"],
		"baseline_digest": _digest(baseline),
		"current_digest": _digest(current),
		"status": status,
		"comparability": {"status": "PASS" if not comparability_reasons else "FAIL", "reasons": comparability_reasons},
		"correctness": {"status": "PASS" if not correctness_reasons else "FAIL", "reasons": correctness_reasons},
		"metrics": metrics,
		"authority": "evidence_only",
	}


def _write_new_json(path: Path, value: dict[str, Any]) -> None:
	if path.exists() or path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)()):
		raise PerformanceError(f"output already exists; choose a new path: {path}")
	if not path.parent.is_dir():
		raise PerformanceError(f"output parent must be an existing directory: {path.parent}")
	content = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False).encode("utf-8") + b"\n"
	if len(content) > MAX_OUTPUT_BYTES:
		raise PerformanceError(f"output exceeds {MAX_OUTPUT_BYTES} bytes")
	temporary: Path | None = None
	try:
		with tempfile.NamedTemporaryFile(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, delete=False) as handle:
			temporary = Path(handle.name)
			handle.write(content)
			handle.flush()
			os.fsync(handle.fileno())
		metadata = temporary.lstat()
		if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
			raise PerformanceError("temporary output was not one regular file")
		os.replace(temporary, path)
	except OSError as exc:
		if temporary is not None:
			temporary.unlink(missing_ok=True)
		raise PerformanceError(f"could not write output: {exc}") from exc


def _markdown_cell(value: Any) -> str:
	if value is None:
		return "N/A"
	return str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(report: dict[str, Any], *, validation: bool) -> str:
	"""Render a small human review surface from already-validated evidence."""
	if validation:
		workload = report["workload"]
		environment = report["environment"]
		return "\n".join((
			f"# Performance result: {report['status']}",
			"",
			"| Field | Value |",
			"|---|---|",
			f"| Result ID | {_markdown_cell(report['result_id'])} |",
			f"| Workload | {_markdown_cell(workload['id'])} |",
			f"| Mode / samples | {_markdown_cell(workload['mode'])} / {_markdown_cell(workload['sample_count'])} |",
			f"| Runtime / target | {_markdown_cell(environment['runtime'])} / {_markdown_cell(environment['target'])} |",
			f"| Correctness | {_markdown_cell(report['correctness']['status'])} |",
			f"| Metrics | {_markdown_cell(', '.join(report['metric_names']))} |",
			f"| Result digest | {_markdown_cell(report['result_digest'])} |",
		))
	lines = [
		f"# Performance comparison: {report['status']}",
		"",
		f"- Budget: `{report['budget_id']}`",
		f"- Comparable: `{report['comparability']['status']}`",
		f"- Correctness: `{report['correctness']['status']}`",
	]
	if report["comparability"]["reasons"]:
		lines.append(f"- Comparability reasons: `{', '.join(report['comparability']['reasons'])}`")
	if report["correctness"]["reasons"]:
		lines.append(f"- Correctness reasons: `{', '.join(report['correctness']['reasons'])}`")
	lines.extend((
		"",
		"| Metric | Direction | Baseline | Current | Limit | Regression ppm | Status | Reason |",
		"|---|---|---:|---:|---:|---:|---|---|",
	))
	for metric in report["metrics"]:
		lines.append(
			"| " + " | ".join(_markdown_cell(metric[field]) for field in (
				"name", "direction", "baseline", "current", "limit", "regression_ppm", "status", "reason",
			)) + " |"
		)
	return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Compare bounded Harness performance results without executing code")
	parser.add_argument("--validate", action="store_true", help="Validate one result instead of comparing baseline/current evidence")
	parser.add_argument("--result", help="Closed JSON result to validate; required with --validate")
	parser.add_argument("--baseline", help="Closed JSON baseline result; required for comparison")
	parser.add_argument("--current", help="Closed JSON candidate result; required for comparison")
	parser.add_argument("--budget", help="Closed JSON performance budget; required for comparison")
	parser.add_argument("--output", help="Write report to a new JSON file; existing files are never overwritten")
	parser.add_argument("--format", choices=("text", "markdown"), default="text", help="Human-readable output format when --json is absent")
	parser.add_argument("--json", action="store_true", help="Print the complete machine-readable report")
	return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
	args = parse_args(argv)
	try:
		if args.json and args.format != "text":
			raise PerformanceError("--json cannot be combined with a non-default --format")
		if args.validate:
			if not args.result or args.baseline or args.current or args.budget:
				raise PerformanceError("--validate requires --result and cannot be combined with comparison inputs")
			result = validate_result(_load_json(Path(args.result), "performance result"))
			report = {
				"schema_version": SCHEMA_VERSION,
				"status": "VALID",
				"result_digest": _digest(result),
				"result_id": result["result_id"],
				"workload": result["workload"],
				"environment": result["environment"],
				"correctness": result["correctness"],
				"metric_names": sorted(result["metrics"]),
				"authority": "evidence_only",
			}
		else:
			if args.result or not args.baseline or not args.current or not args.budget:
				raise PerformanceError("comparison requires --baseline, --current, and --budget without --result")
			report = compare(
				_load_json(Path(args.baseline), "performance baseline"),
				_load_json(Path(args.current), "performance current"),
				_load_json(Path(args.budget), "performance budget"),
			)
		if args.output:
			_write_new_json(Path(args.output), report)
	except (PerformanceError, OSError, ValueError, RecursionError, MemoryError) as exc:
		error = {"schema_version": SCHEMA_VERSION, "status": "ERROR", "error": str(exc)[:2_048]}
		if args.json:
			print(json.dumps(error, ensure_ascii=False, indent=2, sort_keys=True))
		else:
			print(f"Performance check error: {error['error']}", file=sys.stderr)
		return 2
	if args.json:
		print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False))
	elif args.format == "markdown":
		print(render_markdown(report, validation=args.validate))
	else:
		if args.validate:
			print(f"VALID: {report['result_id']}")
		else:
			failed = [metric["name"] for metric in report["metrics"] if metric["status"] != "PASS"]
			print(f"{report['status']}: {report['budget_id']}" + (f"; failed metrics: {', '.join(failed)}" if failed else ""))
		if args.output:
			print(f"Report: {args.output}")
	return 0 if report["status"] in {"PASS", "VALID"} else 1


if __name__ == "__main__":
	raise SystemExit(main())
