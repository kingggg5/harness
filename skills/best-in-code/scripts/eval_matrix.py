#!/usr/bin/env python3
"""Run bounded behavioral evaluations across Harness workflow variants."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

from bounded_json import load_bounded_json, unique_object
from trace_ops import redact_text


SCHEMA_VERSION = 1
VARIANTS = ("single-owner", "full", "ablation")
MAX_SUITE_BYTES = 1024 * 1024
MAX_CASES = 128
MAX_TRIALS = 20
MAX_CONCURRENCY = 8
MAX_JOBS = 1_024
MAX_TIMEOUT_SECONDS = 600
MAX_PROMPT_BYTES = 32 * 1024
MAX_INPUT_BYTES = 64 * 1024
MAX_RUNNER_OUTPUT_BYTES = 1024 * 1024
MAX_RUNNER_ERROR_BYTES = 64 * 1024
MAX_REPORT_BYTES = 8 * 1024 * 1024
MAX_LIST_ITEMS = 128
MAX_LABEL_BYTES = 256
MAX_FAILURES = 32
MAX_METRIC = 10**12
SUITE_FIELDS = {"schema_version", "suite_id", "cases"}
CASE_FIELDS = {"id", "category", "runner", "prompt", "input", "variants", "expectations", "fixtures"}
EXPECTATION_FIELDS = {
	"task_outcome", "policy_compliant", "required_tools", "forbidden_tools",
	"required_events", "forbidden_events", "forbidden_actions",
	"required_retained_markers", "max_context_bytes", "max_tool_output_bytes",
	"max_retries",
}
OBSERVED_FIELDS = {
	"schema_version", "task_outcome", "policy_compliant", "tools", "events",
	"actions", "retained_markers", "metrics",
}
METRIC_FIELDS = {
	"latency_ms", "input_tokens", "output_tokens", "cached_tokens",
	"cost_microusd", "retries", "context_bytes", "max_tool_output_bytes",
}
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
LABEL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
ENV_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


class EvalError(ValueError):
	"""Raised when evaluation input or execution fails closed."""


@dataclass(frozen=True)
class Job:
	case_index: int
	case: dict[str, Any]
	variant: str
	trial: int


def _reject_constant(value: str) -> None:
	raise ValueError(f"non-finite JSON number is not allowed: {value}")


def _json_bytes(value: Any) -> bytes:
	return json.dumps(
		value,
		ensure_ascii=False,
		sort_keys=True,
		separators=(",", ":"),
		allow_nan=False,
	).encode("utf-8")


def _closed_object(value: Any, fields: set[str], label: str) -> dict[str, Any]:
	if not isinstance(value, dict):
		raise EvalError(f"{label} must be an object")
	missing = fields - set(value)
	unknown = set(value) - fields
	if missing:
		raise EvalError(f"{label} is missing fields: {sorted(missing)}")
	if unknown:
		raise EvalError(f"{label} has unknown fields: {sorted(unknown)}")
	return value


def _bounded_integer(value: Any, label: str, *, maximum: int = MAX_METRIC) -> int:
	if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= maximum:
		raise EvalError(f"{label} must be an integer from 0 to {maximum}")
	return value


def _bounded_labels(value: Any, label: str) -> list[str]:
	if not isinstance(value, list) or len(value) > MAX_LIST_ITEMS:
		raise EvalError(f"{label} must be a list with at most {MAX_LIST_ITEMS} values")
	result: list[str] = []
	seen: set[str] = set()
	for index, item in enumerate(value):
		if not isinstance(item, str) or not LABEL_PATTERN.fullmatch(item) or len(item.encode("utf-8")) > MAX_LABEL_BYTES:
			raise EvalError(f"{label}[{index}] is not a safe bounded label")
		if item in seen:
			raise EvalError(f"{label} contains duplicate value {item!r}")
		seen.add(item)
		result.append(item)
	return result


def _validate_json_input(value: Any, label: str, *, depth: int = 0, count: list[int] | None = None) -> None:
	if count is None:
		count = [0]
	if depth > 8:
		raise EvalError(f"{label} exceeds maximum depth 8")
	count[0] += 1
	if count[0] > 1_024:
		raise EvalError(f"{label} exceeds 1024 values")
	if value is None or isinstance(value, bool):
		return
	if isinstance(value, int):
		if abs(value) > MAX_METRIC:
			raise EvalError(f"{label} integer is outside the supported range")
		return
	if isinstance(value, float):
		if not math.isfinite(value) or abs(value) > MAX_METRIC:
			raise EvalError(f"{label} number is outside the supported range")
		return
	if isinstance(value, str):
		if "\x00" in value or len(value.encode("utf-8")) > MAX_PROMPT_BYTES:
			raise EvalError(f"{label} contains a string that is too large or has NUL")
		return
	if isinstance(value, list):
		if len(value) > MAX_LIST_ITEMS:
			raise EvalError(f"{label} contains too many list items")
		for index, item in enumerate(value):
			_validate_json_input(item, f"{label}[{index}]", depth=depth + 1, count=count)
		return
	if isinstance(value, dict):
		if len(value) > MAX_LIST_ITEMS:
			raise EvalError(f"{label} contains too many object fields")
		for key, item in value.items():
			if not isinstance(key, str) or not key or "\x00" in key or len(key.encode("utf-8")) > 128:
				raise EvalError(f"{label} contains an invalid object key")
			_validate_json_input(item, f"{label}.{key}", depth=depth + 1, count=count)
		return
	raise EvalError(f"{label} contains unsupported value type {type(value).__name__}")


def validate_observed(value: Any, label: str = "observed") -> dict[str, Any]:
	observed = _closed_object(value, OBSERVED_FIELDS, label)
	if observed["schema_version"] != SCHEMA_VERSION:
		raise EvalError(f"{label}.schema_version must be {SCHEMA_VERSION}")
	for field in ("task_outcome", "policy_compliant"):
		if not isinstance(observed[field], bool):
			raise EvalError(f"{label}.{field} must be boolean")
	for field in ("tools", "events", "actions", "retained_markers"):
		_bounded_labels(observed[field], f"{label}.{field}")
	metrics = _closed_object(observed["metrics"], METRIC_FIELDS, f"{label}.metrics")
	for field in METRIC_FIELDS:
		_bounded_integer(metrics[field], f"{label}.metrics.{field}")
	return observed


def _validate_expectations(value: Any, label: str) -> dict[str, Any]:
	expectations = _closed_object(value, EXPECTATION_FIELDS, label)
	for field in ("task_outcome", "policy_compliant"):
		if not isinstance(expectations[field], bool):
			raise EvalError(f"{label}.{field} must be boolean")
	for field in (
		"required_tools", "forbidden_tools", "required_events", "forbidden_events",
		"forbidden_actions", "required_retained_markers",
	):
		_bounded_labels(expectations[field], f"{label}.{field}")
	for field in ("max_context_bytes", "max_tool_output_bytes", "max_retries"):
		_bounded_integer(expectations[field], f"{label}.{field}")
	for required, forbidden in (
		("required_tools", "forbidden_tools"),
		("required_events", "forbidden_events"),
	):
		overlap = set(expectations[required]) & set(expectations[forbidden])
		if overlap:
			raise EvalError(f"{label} requires and forbids the same labels: {sorted(overlap)}")
	return expectations


def validate_suite(value: Any) -> dict[str, Any]:
	"""Validate and return a closed, bounded behavioral suite."""
	suite = _closed_object(value, SUITE_FIELDS, "suite")
	if suite["schema_version"] != SCHEMA_VERSION:
		raise EvalError(f"suite.schema_version must be {SCHEMA_VERSION}")
	if not isinstance(suite["suite_id"], str) or not ID_PATTERN.fullmatch(suite["suite_id"]):
		raise EvalError("suite.suite_id is invalid")
	cases = suite["cases"]
	if not isinstance(cases, list) or not 1 <= len(cases) <= MAX_CASES:
		raise EvalError(f"suite.cases must contain 1 to {MAX_CASES} cases")
	seen_ids: set[str] = set()
	for case_index, raw_case in enumerate(cases):
		label = f"suite.cases[{case_index}]"
		case = _closed_object(raw_case, CASE_FIELDS, label)
		if not isinstance(case["id"], str) or not ID_PATTERN.fullmatch(case["id"]):
			raise EvalError(f"{label}.id is invalid")
		if case["id"] in seen_ids:
			raise EvalError(f"duplicate case id: {case['id']}")
		seen_ids.add(case["id"])
		if not isinstance(case["category"], str) or not ID_PATTERN.fullmatch(case["category"]):
			raise EvalError(f"{label}.category is invalid")
		if case["runner"] not in {"local", "external"}:
			raise EvalError(f"{label}.runner must be local or external")
		if not isinstance(case["prompt"], str) or not case["prompt"].strip() or "\x00" in case["prompt"]:
			raise EvalError(f"{label}.prompt must be non-empty text without NUL")
		if len(case["prompt"].encode("utf-8")) > MAX_PROMPT_BYTES:
			raise EvalError(f"{label}.prompt exceeds {MAX_PROMPT_BYTES} bytes")
		if not isinstance(case["input"], dict):
			raise EvalError(f"{label}.input must be an object")
		_validate_json_input(case["input"], f"{label}.input")
		if len(_json_bytes(case["input"])) > MAX_INPUT_BYTES:
			raise EvalError(f"{label}.input exceeds {MAX_INPUT_BYTES} canonical bytes")
		variants = case["variants"]
		if not isinstance(variants, list) or not variants:
			raise EvalError(f"{label}.variants must be a non-empty list")
		if len(set(variants)) != len(variants) or any(variant not in VARIANTS for variant in variants):
			raise EvalError(f"{label}.variants must be unique values from {list(VARIANTS)}")
		_validate_expectations(case["expectations"], f"{label}.expectations")
		fixtures = case["fixtures"]
		if not isinstance(fixtures, dict):
			raise EvalError(f"{label}.fixtures must be an object")
		unknown_fixtures = set(fixtures) - set(variants)
		if unknown_fixtures:
			raise EvalError(f"{label}.fixtures has variants not selected by the case: {sorted(unknown_fixtures)}")
		if case["runner"] == "local" and set(fixtures) != set(variants):
			raise EvalError(f"{label}.fixtures must define every local variant")
		for variant, fixture in fixtures.items():
			validate_observed(fixture, f"{label}.fixtures.{variant}")
	return suite


def load_suite(path: Path) -> dict[str, Any]:
	value, errors = load_bounded_json(path, max_bytes=MAX_SUITE_BYTES, label="behavior suite")
	if errors:
		raise EvalError(" | ".join(errors))
	return validate_suite(value)


def parse_runner_argv(raw: str | None, label: str) -> list[str] | None:
	if raw is None:
		return None
	try:
		value = json.loads(raw, object_pairs_hook=unique_object, parse_constant=_reject_constant)
	except (json.JSONDecodeError, ValueError, RecursionError, MemoryError) as exc:
		raise EvalError(f"{label} must be a JSON array of argv strings: {exc}") from exc
	if not isinstance(value, list) or not 1 <= len(value) <= 32:
		raise EvalError(f"{label} must contain 1 to 32 argv strings")
	argv: list[str] = []
	for index, item in enumerate(value):
		if not isinstance(item, str) or not item or "\x00" in item or len(item.encode("utf-8")) > 4_096:
			raise EvalError(f"{label}[{index}] is invalid or exceeds 4096 bytes")
		argv.append(item)
	return argv


def _runner_environment(extra_names: list[str]) -> dict[str, str]:
	allowed = {
		"PATH", "Path", "PATHEXT", "SYSTEMROOT", "SystemRoot", "WINDIR",
		"COMSPEC", "TEMP", "TMP", "LANG", "LC_ALL", "PYTHONPATH",
		"PYTHONHOME", "VIRTUAL_ENV",
	}
	for name in extra_names:
		if not ENV_NAME_PATTERN.fullmatch(name):
			raise EvalError(f"invalid runner environment variable name: {name!r}")
		allowed.add(name)
	return {name: value for name, value in os.environ.items() if name in allowed}


def _run_subprocess(
	argv: list[str],
	payload: dict[str, Any],
	*,
	timeout_seconds: int,
	environment: dict[str, str],
) -> tuple[dict[str, Any] | None, int, str | None]:
	request = _json_bytes(payload)
	if len(request) > MAX_INPUT_BYTES + MAX_PROMPT_BYTES + 8 * 1024:
		return None, 0, "runner request exceeds the bounded input limit"
	started = time.monotonic_ns()
	process: subprocess.Popen[bytes] | None = None
	try:
		with tempfile.TemporaryFile() as input_file, tempfile.TemporaryFile() as output_file, tempfile.TemporaryFile() as error_file:
			input_file.write(request)
			input_file.seek(0)
			creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
			process = subprocess.Popen(
				argv,
				stdin=input_file,
				stdout=output_file,
				stderr=error_file,
				shell=False,
				env=environment,
				close_fds=True,
				creationflags=creation_flags,
			)
			deadline = time.monotonic() + timeout_seconds
			failure: str | None = None
			while process.poll() is None:
				if time.monotonic() >= deadline:
					failure = f"runner timed out after {timeout_seconds} seconds"
					process.kill()
					break
				if output_file.tell() > MAX_RUNNER_OUTPUT_BYTES or error_file.tell() > MAX_RUNNER_ERROR_BYTES:
					failure = "runner output exceeded the bounded output limit"
					process.kill()
					break
				time.sleep(0.01)
			process.wait(timeout=5)
			wall_ms = max(0, (time.monotonic_ns() - started) // 1_000_000)
			output_size = output_file.tell()
			error_size = error_file.tell()
			output_file.seek(0)
			error_file.seek(0)
			stdout = output_file.read(MAX_RUNNER_OUTPUT_BYTES + 1)
			stderr = error_file.read(MAX_RUNNER_ERROR_BYTES + 1)
			if failure is not None:
				return None, wall_ms, failure
			if output_size > MAX_RUNNER_OUTPUT_BYTES or error_size > MAX_RUNNER_ERROR_BYTES:
				return None, wall_ms, "runner output exceeded the bounded output limit"
			if process.returncode != 0:
				detail = redact_text(stderr.decode("utf-8", errors="replace"))[:2_048].strip()
				return None, wall_ms, f"runner exited with code {process.returncode}: {detail or 'no diagnostic'}"
			try:
				value = json.loads(
					stdout.decode("utf-8"),
					object_pairs_hook=unique_object,
					parse_constant=_reject_constant,
				)
				return validate_observed(value), wall_ms, None
			except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError, MemoryError) as exc:
				return None, wall_ms, f"runner returned invalid observed JSON: {redact_text(str(exc))[:1_024]}"
	except (OSError, subprocess.SubprocessError) as exc:
		if process is not None and process.poll() is None:
			process.kill()
		return None, max(0, (time.monotonic_ns() - started) // 1_000_000), f"could not run evaluator argv: {redact_text(str(exc))[:1_024]}"


def _contains_all(observed: list[str], required: list[str]) -> bool:
	return set(required).issubset(observed)


def _contains_none(observed: list[str], forbidden: list[str]) -> bool:
	return set(observed).isdisjoint(forbidden)


def score_observed(observed: dict[str, Any], expectations: dict[str, Any], wall_latency_ms: int) -> dict[str, Any]:
	metrics = observed["metrics"]
	failures: list[str] = []
	task_check = observed["task_outcome"] is expectations["task_outcome"]
	if not task_check:
		failures.append("task_outcome did not match")
	policy_check = observed["policy_compliant"] is expectations["policy_compliant"]
	if not _contains_all(observed["events"], expectations["required_events"]):
		policy_check = False
		failures.append("required policy events were missing")
	if not _contains_none(observed["events"], expectations["forbidden_events"]):
		policy_check = False
		failures.append("forbidden policy events were observed")
	if not _contains_none(observed["actions"], expectations["forbidden_actions"]):
		policy_check = False
		failures.append("forbidden actions were observed")
	if metrics["retries"] > expectations["max_retries"]:
		policy_check = False
		failures.append("retry limit was exceeded")
	if observed["policy_compliant"] is not expectations["policy_compliant"]:
		failures.append("policy_compliant did not match")
	tool_check = _contains_all(observed["tools"], expectations["required_tools"])
	if not tool_check:
		failures.append("required tools were not routed")
	if not _contains_none(observed["tools"], expectations["forbidden_tools"]):
		tool_check = False
		failures.append("forbidden tools were routed")
	context_check = _contains_all(observed["retained_markers"], expectations["required_retained_markers"])
	if not context_check:
		failures.append("required context markers were not retained")
	if metrics["context_bytes"] > expectations["max_context_bytes"]:
		context_check = False
		failures.append("context byte limit was exceeded")
	if metrics["max_tool_output_bytes"] > expectations["max_tool_output_bytes"]:
		context_check = False
		failures.append("tool output byte limit was exceeded")
	checks = {
		"task_outcome": task_check,
		"policy": policy_check,
		"tool_routing": tool_check,
		"context": context_check,
	}
	return {
		"status": "PASSED" if all(checks.values()) else "FAILED",
		"checks": checks,
		"failures": failures[:MAX_FAILURES],
		"metrics": {
			**metrics,
			"evaluator_wall_latency_ms": wall_latency_ms,
			"total_tokens": metrics["input_tokens"] + metrics["output_tokens"],
		},
	}


def _execute_job(
	job: Job,
	*,
	suite_id: str,
	local_argv: list[str] | None,
	external_argv: list[str] | None,
	require_external: bool,
	timeout_seconds: int,
	environment: dict[str, str],
) -> dict[str, Any]:
	case = job.case
	base = {
		"case_index": job.case_index,
		"case_id": case["id"],
		"category": case["category"],
		"runner": case["runner"],
		"variant": job.variant,
		"trial": job.trial,
	}
	argv = local_argv if case["runner"] == "local" else external_argv
	if case["runner"] == "external" and argv is None:
		if require_external:
			return {**base, "status": "FAILED", "checks": None, "failures": ["external runner is required but was not configured"], "metrics": None}
		return {**base, "status": "SKIPPED", "checks": None, "failures": ["external runner was not configured"], "metrics": None}
	if case["runner"] == "local" and argv is None:
		observed = case["fixtures"][job.variant]
		wall_ms = observed["metrics"]["latency_ms"]
	else:
		request = {
			"schema_version": SCHEMA_VERSION,
			"suite_id": suite_id,
			"case_id": case["id"],
			"category": case["category"],
			"variant": job.variant,
			"trial": job.trial,
			"prompt": case["prompt"],
			"input": case["input"],
		}
		observed, wall_ms, error = _run_subprocess(
			argv,
			request,
			timeout_seconds=timeout_seconds,
			environment=environment,
		)
		if error is not None or observed is None:
			return {**base, "status": "FAILED", "checks": None, "failures": [error or "runner failed closed"], "metrics": {"evaluator_wall_latency_ms": wall_ms}}
	scored = score_observed(observed, case["expectations"], wall_ms)
	return {**base, **scored}


def _nearest_rank(values: list[int], percentile: float) -> int | None:
	if not values:
		return None
	ordered = sorted(values)
	index = max(0, math.ceil(percentile * len(ordered)) - 1)
	return ordered[index]


def _mean(values: list[int]) -> float | None:
	if not values:
		return None
	return round(sum(values) / len(values), 3)


def _rate(numerator: int, denominator: int) -> float | None:
	if denominator == 0:
		return None
	return round(numerator / denominator, 6)


def _aggregate_variant(results: list[dict[str, Any]], variant: str) -> dict[str, Any]:
	items = [item for item in results if item["variant"] == variant]
	scored = [item for item in items if item["status"] in {"PASSED", "FAILED"} and item.get("checks") is not None]
	metrics = [item["metrics"] for item in scored if item.get("metrics") is not None]
	def metric_values(name: str) -> list[int]:
		return [metric[name] for metric in metrics if name in metric and isinstance(metric[name], int)]
	return {
		"total": len(items),
		"passed": sum(item["status"] == "PASSED" for item in items),
		"failed": sum(item["status"] == "FAILED" for item in items),
		"skipped": sum(item["status"] == "SKIPPED" for item in items),
		"task_outcome_rate": _rate(sum(item["checks"]["task_outcome"] for item in scored), len(scored)),
		"policy_pass_rate": _rate(sum(item["checks"]["policy"] for item in scored), len(scored)),
		"tool_routing_pass_rate": _rate(sum(item["checks"]["tool_routing"] for item in scored), len(scored)),
		"context_pass_rate": _rate(sum(item["checks"]["context"] for item in scored), len(scored)),
		"overall_pass_rate": _rate(sum(item["status"] == "PASSED" for item in scored), len(scored)),
		"metrics": {
			name: {"mean": _mean(metric_values(name)), "p95": _nearest_rank(metric_values(name), 0.95)}
			for name in (
				"latency_ms", "evaluator_wall_latency_ms", "input_tokens", "output_tokens",
				"cached_tokens", "total_tokens", "cost_microusd", "retries", "context_bytes",
				"max_tool_output_bytes",
			)
		},
	}


def evaluate_suite(
	suite: dict[str, Any],
	*,
	trials: int = 1,
	variants: list[str] | None = None,
	concurrency: int = 1,
	timeout_seconds: int = 60,
	local_argv: list[str] | None = None,
	external_argv: list[str] | None = None,
	require_external: bool = False,
	runner_env_names: list[str] | None = None,
) -> dict[str, Any]:
	"""Execute a validated suite and return a deterministic machine-readable report."""
	validate_suite(suite)
	if not 1 <= trials <= MAX_TRIALS:
		raise EvalError(f"trials must be from 1 to {MAX_TRIALS}")
	if not 1 <= concurrency <= MAX_CONCURRENCY:
		raise EvalError(f"concurrency must be from 1 to {MAX_CONCURRENCY}")
	if not 1 <= timeout_seconds <= MAX_TIMEOUT_SECONDS:
		raise EvalError(f"timeout_seconds must be from 1 to {MAX_TIMEOUT_SECONDS}")
	selected_variants = list(VARIANTS) if variants is None else variants
	if not selected_variants or len(set(selected_variants)) != len(selected_variants) or any(item not in VARIANTS for item in selected_variants):
		raise EvalError(f"variants must be unique values from {list(VARIANTS)}")
	environment = _runner_environment(runner_env_names or [])
	jobs: list[Job] = []
	for case_index, case in enumerate(suite["cases"]):
		for variant in selected_variants:
			if variant not in case["variants"]:
				continue
			for trial in range(1, trials + 1):
				jobs.append(Job(case_index=case_index, case=case, variant=variant, trial=trial))
	if not jobs:
		raise EvalError("no jobs matched the selected variants")
	if len(jobs) > MAX_JOBS:
		raise EvalError(f"evaluation expands to {len(jobs)} jobs; limit is {MAX_JOBS}")
	results: list[dict[str, Any]] = []
	with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="harness-eval") as executor:
		futures = [
			executor.submit(
				_execute_job,
				job,
				suite_id=suite["suite_id"],
				local_argv=local_argv,
				external_argv=external_argv,
				require_external=require_external,
				timeout_seconds=timeout_seconds,
				environment=environment,
			)
			for job in jobs
		]
		for future in as_completed(futures):
			try:
				results.append(future.result())
			except Exception as exc:
				results.append({
					"case_index": MAX_CASES,
					"case_id": "internal-error",
					"category": "evaluator",
					"runner": "local",
					"variant": selected_variants[0],
					"trial": 0,
					"status": "FAILED",
					"checks": None,
					"failures": [f"evaluator worker failed closed: {redact_text(str(exc))[:1_024]}"],
					"metrics": None,
				})
	results.sort(key=lambda item: (item["case_index"], VARIANTS.index(item["variant"]), item["trial"]))
	for item in results:
		item.pop("case_index", None)
	passed = sum(item["status"] == "PASSED" for item in results)
	failed = sum(item["status"] == "FAILED" for item in results)
	skipped = sum(item["status"] == "SKIPPED" for item in results)
	status = "FAIL" if failed else "PASS_WITH_SKIPS" if skipped else "PASS"
	active_variants = [variant for variant in VARIANTS if variant in selected_variants]
	return {
		"schema_version": SCHEMA_VERSION,
		"suite_id": suite["suite_id"],
		"settings": {
			"trials": trials,
			"variants": selected_variants,
			"concurrency": concurrency,
			"timeout_seconds": timeout_seconds,
			"local_runner": "argv" if local_argv else "fixture",
			"external_runner_configured": external_argv is not None,
			"require_external": require_external,
			"runner_environment_names": sorted(runner_env_names or []),
		},
		"summary": {
			"status": status,
			"total": len(results),
			"passed": passed,
			"failed": failed,
			"skipped": skipped,
			"by_variant": {variant: _aggregate_variant(results, variant) for variant in active_variants},
		},
		"results": results,
	}


def _bounded_cli_int(low: int, high: int):
	def parse(value: str) -> int:
		try:
			parsed = int(value)
		except ValueError as exc:
			raise argparse.ArgumentTypeError("must be an integer") from exc
		if not low <= parsed <= high:
			raise argparse.ArgumentTypeError(f"must be from {low} to {high}")
		return parsed
	return parse


def _write_new_report(path: Path, report: dict[str, Any]) -> None:
	if path.exists() or path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)()):
		raise EvalError(f"report output already exists; choose a new path: {path}")
	if not path.parent.exists() or not path.parent.is_dir():
		raise EvalError(f"report output parent must be an existing directory: {path.parent}")
	content = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False).encode("utf-8") + b"\n"
	if len(content) > MAX_REPORT_BYTES:
		raise EvalError(f"report exceeds {MAX_REPORT_BYTES} bytes")
	temporary_path: Path | None = None
	try:
		with tempfile.NamedTemporaryFile(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, delete=False) as handle:
			temporary_path = Path(handle.name)
			handle.write(content)
			handle.flush()
			os.fsync(handle.fileno())
		metadata = temporary_path.lstat()
		if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
			raise EvalError("temporary report was not one regular file")
		os.replace(temporary_path, path)
	except OSError as exc:
		if temporary_path is not None:
			temporary_path.unlink(missing_ok=True)
		raise EvalError(f"could not write report: {exc}") from exc


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Run bounded Harness behavioral evaluations")
	parser.add_argument("--suite", required=True, help="Path to a closed-schema behavior suite")
	parser.add_argument("--trials", type=_bounded_cli_int(1, MAX_TRIALS), default=1)
	parser.add_argument("--variant", action="append", choices=VARIANTS, dest="variants", help="Select a variant; repeat to select more")
	parser.add_argument("--concurrency", type=_bounded_cli_int(1, MAX_CONCURRENCY), default=1)
	parser.add_argument("--timeout-seconds", type=_bounded_cli_int(1, MAX_TIMEOUT_SECONDS), default=60)
	parser.add_argument("--local-runner-argv", help="Exact local runner argv as a JSON string array; shell is never used")
	parser.add_argument("--external-runner-argv", help="Exact external runner argv as a JSON string array; shell is never used")
	parser.add_argument("--runner-env", action="append", default=[], help="Explicit environment variable name to pass to runners")
	parser.add_argument("--require-external", action="store_true", help="Fail instead of skip when external cases have no runner")
	parser.add_argument("--output", help="Write JSON report to a new file; existing files are never overwritten")
	parser.add_argument("--json", action="store_true", help="Print the full machine-readable report")
	return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
	args = parse_args(argv)
	try:
		suite = load_suite(Path(args.suite))
		local_argv = parse_runner_argv(args.local_runner_argv, "--local-runner-argv")
		external_argv = parse_runner_argv(args.external_runner_argv, "--external-runner-argv")
		report = evaluate_suite(
			suite,
			trials=args.trials,
			variants=args.variants,
			concurrency=args.concurrency,
			timeout_seconds=args.timeout_seconds,
			local_argv=local_argv,
			external_argv=external_argv,
			require_external=args.require_external,
			runner_env_names=args.runner_env,
		)
		if args.output:
			_write_new_report(Path(args.output), report)
	except EvalError as exc:
		error = {"schema_version": SCHEMA_VERSION, "summary": {"status": "ERROR"}, "errors": [redact_text(str(exc))]}
		if args.json:
			print(json.dumps(error, ensure_ascii=False, indent=2, sort_keys=True))
		else:
			print(f"Evaluation error: {error['errors'][0]}", file=sys.stderr)
		return 2
	if args.json:
		print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False))
	else:
		summary = report["summary"]
		print(
			f"{summary['status']}: {summary['passed']} passed, "
			f"{summary['failed']} failed, {summary['skipped']} skipped."
		)
		if args.output:
			print(f"Report: {args.output}")
	return 1 if report["summary"]["status"] == "FAIL" else 0


if __name__ == "__main__":
	raise SystemExit(main())
