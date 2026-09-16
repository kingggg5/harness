#!/usr/bin/env python3
"""Bounded semantic decision runtime for Harness.

The first provider is deliberately deterministic and dependency-free. It emits
typed, probabilistic recommendations for routing and semantic checks; policy,
human approval, and tool execution remain outside this module.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

from bounded_json import load_bounded_json, unique_object


SCHEMA_VERSION = 1
MAX_INPUT_BYTES = 256 * 1024
MAX_QUESTIONS = 32
MAX_OPTIONS = 16
MAX_CASES = 256
MAX_TRIALS = 20
MAX_NODES = 4_096
MAX_DEPTH = 10
MAX_STRING_BYTES = 32 * 1024
MAX_ID_BYTES = 128
MAX_OUTPUT_BYTES = 4 * 1024 * 1024
DEFAULT_POLICY = {
	"version": 1,
	"minimum_confidence": 0.75,
	"risk_human_threshold": 0.60,
	"security_human_threshold": 0.70,
}
ID_PATTERN = re.compile(r"^[a-z][a-z0-9._:-]{0,63}$")
OPTION_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9._:-]{0,63}$")
QUESTION_TYPES = {"bool", "choice", "score"}
QUESTION_FIELDS = {"id", "type", "options", "minimum", "maximum"}
SUITE_FIELDS = {"schema_version", "suite_id", "questions", "cases"}
CASE_FIELDS = {"id", "state", "expected"}


class DecisionError(ValueError):
	"""Raised when a decision input is malformed or exceeds a bound."""


def _reject_constant(value: str) -> None:
	raise ValueError(f"non-finite JSON number is not allowed: {value}")


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
		raise DecisionError(f"value cannot be encoded as bounded JSON: {exc}") from exc


def _validate_tree(value: Any, label: str) -> None:
	nodes = [0]

	def visit(item: Any, path: str, depth: int) -> None:
		if depth > MAX_DEPTH:
			raise DecisionError(f"{path} exceeds maximum depth {MAX_DEPTH}")
		nodes[0] += 1
		if nodes[0] > MAX_NODES:
			raise DecisionError(f"{label} exceeds {MAX_NODES} values")
		if item is None or isinstance(item, bool):
			return
		if isinstance(item, int):
			if abs(item) > 10**15:
				raise DecisionError(f"{path} integer is outside the supported range")
			return
		if isinstance(item, float):
			if not math.isfinite(item) or abs(item) > 10**15:
				raise DecisionError(f"{path} number is outside the supported range")
			return
		if isinstance(item, str):
			if "\x00" in item or len(item.encode("utf-8")) > MAX_STRING_BYTES:
				raise DecisionError(f"{path} contains an invalid or oversized string")
			return
		if isinstance(item, list):
			if len(item) > MAX_OPTIONS * MAX_QUESTIONS:
				raise DecisionError(f"{path} contains too many list items")
			for index, child in enumerate(item):
				visit(child, f"{path}[{index}]", depth + 1)
			return
		if isinstance(item, dict):
			if len(item) > MAX_NODES:
				raise DecisionError(f"{path} contains too many object fields")
			for key, child in item.items():
				if not isinstance(key, str) or not key or "\x00" in key or len(key.encode("utf-8")) > MAX_ID_BYTES:
					raise DecisionError(f"{path} contains an invalid object key")
				visit(child, f"{path}.{key}", depth + 1)
			return
		raise DecisionError(f"{path} contains unsupported value type {type(item).__name__}")

	visit(value, label, 0)


def _load_json(path: Path, *, label: str) -> Any:
	value, errors = load_bounded_json(path, max_bytes=MAX_INPUT_BYTES, label=label)
	if errors:
		raise DecisionError(" | ".join(errors))
	_validate_tree(value, label)
	if len(_canonical_json(value)) > MAX_INPUT_BYTES:
		raise DecisionError(f"{label} exceeds {MAX_INPUT_BYTES} canonical bytes")
	return value


def _closed_object(value: Any, fields: set[str], label: str) -> dict[str, Any]:
	if not isinstance(value, dict):
		raise DecisionError(f"{label} must be an object")
	unknown = set(value) - fields
	if unknown:
		raise DecisionError(f"{label} has unknown fields: {sorted(unknown)}")
	return value


def _safe_id(value: Any, label: str) -> str:
	if not isinstance(value, str) or not ID_PATTERN.fullmatch(value):
		raise DecisionError(f"{label} must be a lowercase bounded identifier")
	return value


def _safe_number(value: Any, label: str) -> float:
	if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
		raise DecisionError(f"{label} must be a finite number")
	return float(value)


def validate_questions(value: Any) -> dict[str, Any]:
	questions_doc = _closed_object(value, {"schema_version", "questions"}, "questions")
	if questions_doc.get("schema_version") != SCHEMA_VERSION:
		raise DecisionError(f"questions.schema_version must be {SCHEMA_VERSION}")
	questions = questions_doc.get("questions")
	if not isinstance(questions, list) or not 1 <= len(questions) <= MAX_QUESTIONS:
		raise DecisionError(f"questions.questions must contain 1 to {MAX_QUESTIONS} items")
	seen: set[str] = set()
	validated: list[dict[str, Any]] = []
	for index, raw in enumerate(questions):
		label = f"questions.questions[{index}]"
		question = _closed_object(raw, QUESTION_FIELDS, label)
		identifier = _safe_id(question.get("id"), f"{label}.id")
		if identifier in seen:
			raise DecisionError(f"duplicate question id: {identifier}")
		seen.add(identifier)
		kind = question.get("type")
		if kind not in QUESTION_TYPES:
			raise DecisionError(f"{label}.type must be one of {sorted(QUESTION_TYPES)}")
		if kind == "bool":
			if any(field in question for field in ("options", "minimum", "maximum")):
				raise DecisionError(f"{label} bool questions cannot declare options or score bounds")
			validated.append({"id": identifier, "type": kind})
			continue
		if kind == "choice":
			options = question.get("options")
			if not isinstance(options, list) or not 2 <= len(options) <= MAX_OPTIONS:
				raise DecisionError(f"{label}.options must contain 2 to {MAX_OPTIONS} items")
			clean_options: list[str] = []
			for option_index, option in enumerate(options):
				if not isinstance(option, str) or not OPTION_PATTERN.fullmatch(option):
					raise DecisionError(f"{label}.options[{option_index}] is invalid")
				if option in clean_options:
					raise DecisionError(f"{label}.options contains a duplicate")
				clean_options.append(option)
			validated.append({"id": identifier, "type": kind, "options": clean_options})
			continue
		minimum = _safe_number(question.get("minimum", 0), f"{label}.minimum")
		maximum = _safe_number(question.get("maximum", 1), f"{label}.maximum")
		if minimum >= maximum:
			raise DecisionError(f"{label} minimum must be less than maximum")
		validated.append({"id": identifier, "type": kind, "minimum": minimum, "maximum": maximum})
	return {"schema_version": SCHEMA_VERSION, "questions": validated}


def _text_from_state(state: Any) -> str:
	parts: list[str] = []
	remaining = 32 * 1024

	def visit(item: Any) -> None:
		nonlocal remaining
		if remaining <= 0:
			return
		if isinstance(item, str):
			encoded = item.encode("utf-8")[:remaining]
			parts.append(encoded.decode("utf-8", errors="ignore"))
			remaining -= len(encoded)
		elif isinstance(item, list):
			for child in item:
				visit(child)
		elif isinstance(item, dict):
			for child in item.values():
				visit(child)

	visit(state)
	return " ".join(parts).casefold()


def _has(text: str, patterns: tuple[str, ...]) -> bool:
	return any(re.search(rf"\b{re.escape(pattern)}\b", text) for pattern in patterns)


def _features(state: Any) -> dict[str, float | bool]:
	text = _text_from_state(state)
	quick = _has(text, ("typo", "spelling", "rename", "format", "copy", "docs", "documentation", "style"))
	standard = _has(text, ("api", "endpoint", "feature", "refactor", "integration", "database", "bug", "test"))
	full = _has(text, ("production", "deploy", "migration", "authentication", "authorization", "payment", "security", "vulnerability", "scale", "architecture", "compliance", "incident", "delete", "publish"))
	research = _has(text, ("research", "latest", "compare", "investigate", "unknown", "documentation", "vulnerability", "security"))
	parallel = _has(text, ("parallel", "multi-agent", "multi agent", "frontend", "backend", "graph", "independent", "worktree"))
	security = _has(text, ("security", "auth", "credential", "secret", "permission", "vulnerability", "privacy", "compliance"))
	human = _has(text, ("production", "deploy", "delete", "publish", "payment", "credential", "external", "approval", "legal", "compliance"))
	risk = min(0.99, 0.04 + 0.16 * int(standard) + 0.28 * int(full) + 0.12 * int(security) + 0.08 * int(human))
	complexity = min(0.99, 0.08 + 0.18 * int(standard) + 0.25 * int(full) + 0.12 * int(parallel) + 0.1 * int(research))
	if full or (security and complexity >= 0.3):
		route = "full"
		route_probs = {"quick": 0.04, "standard": 0.16, "full": 0.80}
	elif standard or research or parallel:
		route = "standard"
		route_probs = {"quick": 0.10, "standard": 0.78, "full": 0.12}
	else:
		route = "quick"
		route_probs = {"quick": 0.92, "standard": 0.07, "full": 0.01}
	research_probability = min(0.98, 0.04 + 0.65 * int(research) + 0.18 * int(full) + 0.12 * int(security))
	parallel_probability = min(0.98, 0.03 + 0.65 * int(parallel) + 0.12 * int(standard and not quick))
	human_probability = min(0.99, 0.03 + 0.65 * int(human) + 0.55 * int(security) + 0.24 * risk)
	return {
		"route": route,
		"route_probs": route_probs,
		"risk": risk,
		"complexity": complexity,
		"security": min(0.99, 0.03 + 0.75 * int(security) + 0.15 * risk),
		"research": research_probability,
		"parallel": parallel_probability,
		"human": human_probability,
		"deep": min(0.98, 0.05 + 0.55 * int(full) + 0.2 * complexity),
		"confidence": min(0.99, 0.72 + 0.2 * int(bool(text)) + 0.05 * int(quick or standard or full)),
	}


def _bool_probability(identifier: str, features: dict[str, float | bool]) -> float:
	name = identifier.casefold()
	if "human" in name or "gate" in name or "approval" in name:
		return float(features["human"])
	if "research" in name:
		return float(features["research"])
	if "parallel" in name or "multi" in name:
		return float(features["parallel"])
	if "security" in name or "sensitive" in name:
		return float(features["security"])
	if "deep" in name or "reason" in name:
		return float(features["deep"])
	return 0.5


def _score_value(identifier: str, features: dict[str, float | bool]) -> float:
	name = identifier.casefold()
	if "security" in name or "sensitive" in name:
		return float(features["security"])
	if "complex" in name:
		return float(features["complexity"])
	if "confidence" in name:
		return float(features["confidence"])
	return float(features["risk"])


def evaluate_policy(decision: dict[str, Any], *, policy: dict[str, float] | None = None) -> dict[str, Any]:
	"""Apply deterministic safety floors to a recommendation.

	This produces an advisory routing result. It cannot authorize a tool or
	replace the execution kernel's capability and human-gate checks.
	"""
	settings = {**DEFAULT_POLICY, **(policy or {})}
	minimum_confidence = _safe_number(settings["minimum_confidence"], "policy.minimum_confidence")
	risk_threshold = _safe_number(settings["risk_human_threshold"], "policy.risk_human_threshold")
	security_threshold = _safe_number(settings["security_human_threshold"], "policy.security_human_threshold")
	if not 0 <= minimum_confidence <= 1 or not 0 <= risk_threshold <= 1 or not 0 <= security_threshold <= 1:
		raise DecisionError("policy thresholds must be between 0 and 1")
	decisions = decision.get("decisions")
	if not isinstance(decisions, dict):
		raise DecisionError("decision.decisions must be an object")
	recommended_route = decisions.get("route", {}).get("value", "standard")
	if recommended_route not in {"quick", "standard", "full"}:
		recommended_route = "standard"
	confidence = _safe_number(decision.get("confidence", 0), "decision.confidence")
	reasons: list[str] = []
	requires_human = False
	if confidence < minimum_confidence:
		requires_human = True
		reasons.append("LOW_CONFIDENCE")
	needs_human = decisions.get("needs_human", {})
	if needs_human.get("type") == "bool" and needs_human.get("value") is True:
		requires_human = True
		reasons.append("MODEL_RECOMMENDED_HUMAN")
	risk = decisions.get("risk", {}).get("value")
	if isinstance(risk, (int, float)) and not isinstance(risk, bool) and risk >= risk_threshold:
		requires_human = True
		reasons.append("RISK_THRESHOLD")
	security_risk = decisions.get("security_risk", {}).get("value")
	if isinstance(security_risk, (int, float)) and not isinstance(security_risk, bool) and security_risk >= security_threshold:
		requires_human = True
		reasons.append("SECURITY_THRESHOLD")
	return {
		"version": int(settings["version"]),
		"status": "HUMAN_REQUIRED" if requires_human else "ADVISORY",
		"recommended_route": recommended_route,
		"effective_next_step": "human_approval" if requires_human else f"run_{recommended_route}_policy",
		"requires_human": requires_human,
		"reasons": reasons,
		"thresholds": {
			"minimum_confidence": minimum_confidence,
			"risk_human_threshold": risk_threshold,
			"security_human_threshold": security_threshold,
		},
		"authority": "advisory_only",
	}


def decide(state: Any, questions: dict[str, Any], *, provider: str = "deterministic") -> dict[str, Any]:
	if provider != "deterministic":
		raise DecisionError("only the dependency-free deterministic provider is available in decision runtime v1")
	_validate_tree(state, "state")
	state_bytes = _canonical_json(state)
	if len(state_bytes) > MAX_INPUT_BYTES:
		raise DecisionError(f"state exceeds {MAX_INPUT_BYTES} canonical bytes")
	validated_questions = validate_questions(questions)
	features = _features(state)
	decisions: dict[str, dict[str, Any]] = {}
	confidence_values: list[float] = []
	for question in validated_questions["questions"]:
		identifier = question["id"]
		kind = question["type"]
		if kind == "bool":
			probability = _bool_probability(identifier, features)
			confidence = max(probability, 1 - probability)
			decisions[identifier] = {
				"type": "bool",
				"value": probability >= 0.5,
				"probability_true": round(probability, 6),
				"confidence": round(confidence, 6),
			}
		elif kind == "choice":
			options = question["options"]
			base = features["route_probs"] if identifier.casefold() in {"route", "scale", "mode"} else None
			if base is None:
				probabilities = {option: 1 / len(options) for option in options}
			else:
				available = {option: float(base.get(option, 0.0)) for option in options}
				total = sum(available.values())
				probabilities = ({option: value / total for option, value in available.items()} if total else {option: 1 / len(options) for option in options})
			selected = max(options, key=lambda option: (probabilities[option], -options.index(option)))
			confidence = probabilities[selected]
			decisions[identifier] = {
				"type": "choice",
				"value": selected,
				"probabilities": {option: round(probabilities[option], 6) for option in options},
				"confidence": round(confidence, 6),
			}
		else:
			normalized = _score_value(identifier, features)
			value = question["minimum"] + (question["maximum"] - question["minimum"]) * normalized
			decisions[identifier] = {
				"type": "score",
				"value": round(value, 6),
				"confidence": round(float(features["confidence"]), 6),
			}
		confidence_values.append(float(decisions[identifier]["confidence"]))
	result = {
		"schema_version": SCHEMA_VERSION,
		"provider": provider,
		"decision_id": "sha256:" + hashlib.sha256(state_bytes + _canonical_json(validated_questions)).hexdigest(),
		"input_digest": "sha256:" + hashlib.sha256(state_bytes).hexdigest(),
		"recommendation_only": True,
		"policy_authority": False,
		"decisions": decisions,
		"confidence": round(sum(confidence_values) / len(confidence_values), 6) if confidence_values else 0.0,
	}
	result["policy_recommendation"] = evaluate_policy(result)
	return result


def _validate_suite(value: Any) -> dict[str, Any]:
	suite = _closed_object(value, SUITE_FIELDS, "suite")
	if suite.get("schema_version") != SCHEMA_VERSION:
		raise DecisionError(f"suite.schema_version must be {SCHEMA_VERSION}")
	suite_id = _safe_id(suite.get("suite_id"), "suite.suite_id")
	questions = validate_questions(suite.get("questions"))
	cases = suite.get("cases")
	if not isinstance(cases, list) or not 1 <= len(cases) <= MAX_CASES:
		raise DecisionError(f"suite.cases must contain 1 to {MAX_CASES} items")
	question_map = {question["id"]: question for question in questions["questions"]}
	validated_cases: list[dict[str, Any]] = []
	seen: set[str] = set()
	for index, raw_case in enumerate(cases):
		label = f"suite.cases[{index}]"
		case = _closed_object(raw_case, CASE_FIELDS, label)
		case_id = _safe_id(case.get("id"), f"{label}.id")
		if case_id in seen:
			raise DecisionError(f"duplicate case id: {case_id}")
		seen.add(case_id)
		_validate_tree(case.get("state"), f"{label}.state")
		if not isinstance(case.get("state"), dict):
			raise DecisionError(f"{label}.state must be an object")
		expected = case.get("expected")
		if not isinstance(expected, dict) or set(expected) != set(question_map):
			raise DecisionError(f"{label}.expected must contain exactly the question IDs")
		for question_id, expected_value in expected.items():
			question = question_map[question_id]
			if question["type"] == "bool" and not isinstance(expected_value, bool):
				raise DecisionError(f"{label}.expected.{question_id} must be boolean")
			if question["type"] == "choice" and expected_value not in question["options"]:
				raise DecisionError(f"{label}.expected.{question_id} is not a declared option")
			if question["type"] == "score":
				number = _safe_number(expected_value, f"{label}.expected.{question_id}")
				if not question["minimum"] <= number <= question["maximum"]:
					raise DecisionError(f"{label}.expected.{question_id} is outside score bounds")
		validated_cases.append({"id": case_id, "state": case["state"], "expected": expected})
	return {"schema_version": SCHEMA_VERSION, "suite_id": suite_id, "questions": questions["questions"], "cases": validated_cases}


def _nearest_rank(values: list[float], percentile: float) -> float | None:
	if not values:
		return None
	return sorted(values)[max(0, math.ceil(percentile * len(values)) - 1)]


def _rss_bytes() -> int | None:
	try:
		if os.name == "nt":
			from ctypes import wintypes

			class Counters(ctypes.Structure):
				_fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong), ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
			counters = Counters()
			counters.cb = ctypes.sizeof(Counters)
			psapi = ctypes.WinDLL("Psapi.dll")
			kernel32 = ctypes.WinDLL("Kernel32.dll")
			get_memory = psapi.GetProcessMemoryInfo
			get_memory.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
			get_memory.restype = wintypes.BOOL
			if get_memory(kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
				return int(counters.WorkingSetSize)
		elif os.path.isfile("/proc/self/status"):
			for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
				if line.startswith("VmRSS:"):
					return int(line.split()[1]) * 1024
	except (OSError, ValueError, AttributeError, TypeError):
		return None
	return None


def _f1(labels: list[str], predictions: list[str]) -> float | None:
	if not labels:
		return None
	scores: list[float] = []
	for label in sorted(set(labels) | set(predictions)):
		tp = sum(actual == label and predicted == label for actual, predicted in zip(labels, predictions))
		fp = sum(actual != label and predicted == label for actual, predicted in zip(labels, predictions))
		fn = sum(actual == label and predicted != label for actual, predicted in zip(labels, predictions))
		precision = tp / (tp + fp) if tp + fp else 0.0
		recall = tp / (tp + fn) if tp + fn else 0.0
		scores.append(2 * precision * recall / (precision + recall) if precision + recall else 0.0)
	return sum(scores) / len(scores)


def evaluate_suite(suite: dict[str, Any], *, provider: str = "deterministic", trials: int = 1) -> dict[str, Any]:
	suite = _validate_suite(suite)
	if not 1 <= trials <= MAX_TRIALS:
		raise DecisionError(f"trials must be from 1 to {MAX_TRIALS}")
	question_map = {question["id"]: question for question in suite["questions"]}
	results: list[dict[str, Any]] = []
	accuracies: list[bool] = []
	labels_by_question: dict[str, list[str]] = {question_id: [] for question_id in question_map}
	predictions_by_question: dict[str, list[str]] = {question_id: [] for question_id in question_map}
	brier_values: list[float] = []
	calibration: list[tuple[float, bool]] = []
	score_errors: list[float] = []
	latencies: list[float] = []
	start_all = time.perf_counter_ns()
	for trial in range(1, trials + 1):
		for case in suite["cases"]:
			started = time.perf_counter_ns()
			output = decide(case["state"], {"schema_version": SCHEMA_VERSION, "questions": suite["questions"]}, provider=provider)
			latency_ms = (time.perf_counter_ns() - started) / 1_000_000
			latencies.append(latency_ms)
			case_correct = True
			for question_id, question in question_map.items():
				prediction = output["decisions"][question_id]
				expected = case["expected"][question_id]
				if question["type"] == "bool":
					actual_label = str(bool(expected)).lower()
					predicted_label = str(bool(prediction["value"])).lower()
					probability = prediction["probability_true"]
					brier_values.append((probability - (1.0 if expected else 0.0)) ** 2)
					calibration.append((max(probability, 1 - probability), prediction["value"] is expected))
				elif question["type"] == "choice":
					actual_label = str(expected)
					predicted_label = str(prediction["value"])
					probabilities = prediction["probabilities"]
					brier_values.append(sum((float(probabilities.get(option, 0.0)) - (1.0 if option == expected else 0.0)) ** 2 for option in question["options"]))
					calibration.append((prediction["confidence"], prediction["value"] == expected))
				else:
					actual_label = "score"
					predicted_label = "score"
					score_range = question["maximum"] - question["minimum"]
					score_errors.append(abs(float(prediction["value"]) - float(expected)) / score_range)
				if prediction["value"] != expected and question["type"] != "score":
					case_correct = False
				labels_by_question[question_id].append(actual_label)
				predictions_by_question[question_id].append(predicted_label)
			accuracies.append(case_correct)
			results.append({"case_id": case["id"], "trial": trial, "status": "PASS" if case_correct else "FAIL", "decision": output})
	elapsed_seconds = max((time.perf_counter_ns() - start_all) / 1_000_000_000, 1e-9)
	calibration_bins: list[list[tuple[float, bool]]] = [[] for _ in range(10)]
	for confidence, correct in calibration:
		calibration_bins[min(9, int(confidence * 10))].append((confidence, correct))
	ece = 0.0
	total_calibration = len(calibration)
	for bucket in calibration_bins:
		if bucket:
			ece += len(bucket) / total_calibration * abs(sum(item[0] for item in bucket) / len(bucket) - sum(item[1] for item in bucket) / len(bucket))
	macro_f1_values = [_f1(labels_by_question[qid], predictions_by_question[qid]) for qid in question_map if labels_by_question[qid] and question_map[qid]["type"] in {"bool", "choice"}]
	macro_f1_values = [value for value in macro_f1_values if value is not None]
	rss = _rss_bytes()
	return {
		"schema_version": SCHEMA_VERSION,
		"suite_id": suite["suite_id"],
		"provider": provider,
		"settings": {"trials": trials, "cases": len(suite["cases"])},
		"summary": {
			"status": "PASS" if all(accuracies) else "FAIL",
			"total": len(results),
			"passed": sum(accuracies),
			"failed": len(accuracies) - sum(accuracies),
		},
		"metrics": {
			"accuracy": round(sum(accuracies) / len(accuracies), 6) if accuracies else None,
			"macro_f1": round(sum(macro_f1_values) / len(macro_f1_values), 6) if macro_f1_values else None,
			"brier_score": round(sum(brier_values) / len(brier_values), 6) if brier_values else None,
			"ece": round(ece, 6),
			"score_mae_normalized": round(sum(score_errors) / len(score_errors), 6) if score_errors else None,
			"latency_ms": {"mean": round(sum(latencies) / len(latencies), 6), "p95": round(_nearest_rank(latencies, 0.95) or 0.0, 6)},
			"decisions_per_sec": round(len(results) / elapsed_seconds, 3),
			"rss_mb": round(rss / (1024 * 1024), 3) if rss is not None else None,
		},
		"results": results,
	}


def _print_json(value: Any) -> None:
	content = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
	if len(content.encode("utf-8")) > MAX_OUTPUT_BYTES:
		raise DecisionError("decision output exceeds the bounded output limit")
	print(content)


def _bounded_int(value: str) -> int:
	try:
		parsed = int(value)
	except ValueError as exc:
		raise argparse.ArgumentTypeError("must be an integer") from exc
	return parsed


def main(argv: list[str] | None = None) -> int:
	parser = argparse.ArgumentParser(description="Bounded Harness semantic decision runtime")
	subparsers = parser.add_subparsers(dest="command", required=True)
	decide_parser = subparsers.add_parser("decide", help="recommend typed decisions without executing actions")
	decide_parser.add_argument("--state", required=True)
	decide_parser.add_argument("--questions", required=True)
	decide_parser.add_argument("--provider", default="deterministic", choices=("deterministic",))
	decide_parser.add_argument("--json", action="store_true")
	eval_parser = subparsers.add_parser("eval", help="benchmark a decision provider against labeled cases")
	eval_parser.add_argument("--suite", required=True)
	eval_parser.add_argument("--provider", default="deterministic", choices=("deterministic",))
	eval_parser.add_argument("--trials", type=_bounded_int, default=1)
	eval_parser.add_argument("--json", action="store_true")
	args = parser.parse_args(argv)
	try:
		if args.command == "decide":
			output = decide(_load_json(Path(args.state), label="decision state"), _load_json(Path(args.questions), label="decision questions"), provider=args.provider)
		else:
			output = evaluate_suite(_load_json(Path(args.suite), label="decision suite"), provider=args.provider, trials=args.trials)
	except (DecisionError, OSError, ValueError, RecursionError, MemoryError) as exc:
		error = {"schema_version": SCHEMA_VERSION, "status": "ERROR", "error": str(exc)[:2_048]}
		if args.json:
			_print_json(error)
		else:
			print(f"Decision error: {error['error']}", file=sys.stderr)
		return 2
	try:
		if args.json:
			_print_json(output)
		else:
			if args.command == "eval":
				print(f"{output['summary']['status']}: {output['summary']['passed']} passed, {output['summary']['failed']} failed")
			else:
				print(json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
	except DecisionError as exc:
		error = {"schema_version": SCHEMA_VERSION, "status": "ERROR", "error": str(exc)[:2_048]}
		if args.json:
			_print_json(error)
		else:
			print(f"Decision error: {error['error']}", file=sys.stderr)
		return 2
	return 0 if args.command == "decide" or output["summary"]["status"] == "PASS" else 1


if __name__ == "__main__":
	raise SystemExit(main())
