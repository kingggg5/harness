#!/usr/bin/env python3
"""Validate, inspect, redact, and dry-run Harness JSONL traces."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import re
import stat
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

from bounded_json import unique_object


SCHEMA_VERSION = 1
MAX_TRACE_BYTES = 8 * 1024 * 1024
MAX_LINE_BYTES = 64 * 1024
MAX_EVENTS = 10_000
MAX_PAYLOAD_DEPTH = 8
MAX_PAYLOAD_ITEMS = 2_048
MAX_STRING_BYTES = 16 * 1024
MAX_ERRORS = 64
GENESIS_HASH = "0" * 64
EVENT_FIELDS = {
	"schema_version", "trace_id", "sequence", "timestamp", "event", "actor",
	"side_effect", "payload", "previous_hash", "hash",
}
SIDE_EFFECTS = {"none", "read", "reversible", "consequential"}
TRACE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
EVENT_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
ACTOR_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SENSITIVE_KEY_PATTERN = re.compile(
	r"(?:authorization|cookie|credential|password|passwd|private[_-]?key|secret|session|token|api[_-]?key)",
	re.IGNORECASE,
)
REDACTION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
	(re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL), "[REDACTED_PRIVATE_KEY]"),
	(re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE), "Bearer [REDACTED_SECRET]"),
	(re.compile(r"\b(?:sk|gh[pousr]|github_pat|xox[baprs])[-_][A-Za-z0-9._-]{8,}\b", re.IGNORECASE), "[REDACTED_SECRET]"),
	(re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED_SECRET]"),
	(re.compile(r"(?i)(https?://[^:/\s]+:)[^@\s]+@"), r"\1[REDACTED_SECRET]@"),
	(re.compile(r"(?i)\b(password|passwd|secret|token|api[_-]?key)\s*[:=]\s*[^\s,;]+"), r"\1=[REDACTED_SECRET]"),
	(re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE), "[REDACTED_EMAIL]"),
	(re.compile(r"(?<!\d)(?:\+?\d[\d .()-]{7,}\d)(?!\d)"), "[REDACTED_PHONE_OR_ID]"),
	(re.compile(r"(?i)\b(?:[A-Z]:\\(?:Users|Documents and Settings)\\|/(?:home|Users)/)[^\\/\s]+"), "[REDACTED_HOME]"),
)


class TraceError(ValueError):
	"""Raised when a trace or trace operation fails closed."""


def _reject_constant(value: str) -> None:
	raise ValueError(f"non-finite JSON number is not allowed: {value}")


def _canonical_bytes(value: Any) -> bytes:
	return json.dumps(
		value,
		ensure_ascii=False,
		sort_keys=True,
		separators=(",", ":"),
		allow_nan=False,
	).encode("utf-8")


def compute_event_hash(event: dict[str, Any]) -> str:
	"""Return the canonical SHA-256 for an event excluding its hash field."""
	body = {key: value for key, value in event.items() if key != "hash"}
	return hashlib.sha256(_canonical_bytes(body)).hexdigest()


def seal_event(event: dict[str, Any], previous_hash: str) -> dict[str, Any]:
	"""Copy an event, bind its previous hash, and compute its canonical hash."""
	sealed = copy.deepcopy(event)
	sealed["previous_hash"] = previous_hash
	sealed["hash"] = compute_event_hash(sealed)
	return sealed


def redact_text(value: str) -> str:
	"""Redact common secret and personal-data patterns from one string."""
	redacted = value
	for pattern, replacement in REDACTION_PATTERNS:
		redacted = pattern.sub(replacement, redacted)
	return redacted


def redact_value(value: Any, *, key: str = "") -> Any:
	"""Return a recursively redacted JSON-compatible value."""
	if key and SENSITIVE_KEY_PATTERN.search(key):
		return "[REDACTED_SECRET]"
	if isinstance(value, dict):
		return {str(item_key): redact_value(item_value, key=str(item_key)) for item_key, item_value in value.items()}
	if isinstance(value, list):
		return [redact_value(item) for item in value]
	if isinstance(value, str):
		return redact_text(value)
	return value


def _read_bounded_bytes(path: Path) -> bytes:
	try:
		if path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)()):
			raise TraceError(f"trace cannot be a symlink or junction: {path}")
		initial = path.lstat()
		if not stat.S_ISREG(initial.st_mode) or initial.st_nlink > 1:
			raise TraceError(f"trace must be one regular non-hard-linked file: {path}")
		if initial.st_size > MAX_TRACE_BYTES:
			raise TraceError(f"trace exceeds {MAX_TRACE_BYTES} bytes")
		flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOINHERIT", 0) | getattr(os, "O_NOFOLLOW", 0)
		descriptor = os.open(path, flags)
		try:
			opened = os.fstat(descriptor)
			if not stat.S_ISREG(opened.st_mode) or opened.st_nlink > 1:
				raise TraceError(f"trace must remain one regular non-hard-linked file: {path}")
			if (initial.st_dev, initial.st_ino) != (opened.st_dev, opened.st_ino):
				raise TraceError(f"trace changed while opening: {path}")
			chunks: list[bytes] = []
			remaining = MAX_TRACE_BYTES + 1
			while remaining > 0:
				chunk = os.read(descriptor, min(64 * 1024, remaining))
				if not chunk:
					break
				chunks.append(chunk)
				remaining -= len(chunk)
			raw = b"".join(chunks)
			final = os.fstat(descriptor)
			if (opened.st_dev, opened.st_ino) != (final.st_dev, final.st_ino) or final.st_size != len(raw):
				raise TraceError(f"trace changed while reading: {path}")
		finally:
			os.close(descriptor)
	except OSError as exc:
		raise TraceError(f"could not read trace: {exc}") from exc
	if len(raw) > MAX_TRACE_BYTES:
		raise TraceError(f"trace exceeds {MAX_TRACE_BYTES} bytes")
	return raw


def _check_timestamp(value: Any) -> bool:
	if not isinstance(value, str) or len(value.encode("utf-8")) > 64:
		return False
	try:
		parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
	except ValueError:
		return False
	return parsed.tzinfo is not None


def _validate_json_value(value: Any, label: str, errors: list[str], *, depth: int = 0, counter: list[int] | None = None) -> None:
	if counter is None:
		counter = [0]
	if len(errors) >= MAX_ERRORS:
		return
	if depth > MAX_PAYLOAD_DEPTH:
		errors.append(f"{label} exceeds maximum depth {MAX_PAYLOAD_DEPTH}")
		return
	counter[0] += 1
	if counter[0] > MAX_PAYLOAD_ITEMS:
		errors.append(f"payload exceeds {MAX_PAYLOAD_ITEMS} values")
		return
	if value is None or isinstance(value, bool):
		return
	if isinstance(value, int):
		if abs(value) > 10**18:
			errors.append(f"{label} integer is outside the supported range")
		return
	if isinstance(value, float):
		if not math.isfinite(value) or abs(value) > 10**18:
			errors.append(f"{label} number is outside the supported range")
		return
	if isinstance(value, str):
		if "\x00" in value or len(value.encode("utf-8")) > MAX_STRING_BYTES:
			errors.append(f"{label} exceeds {MAX_STRING_BYTES} UTF-8 bytes or contains NUL")
		return
	if isinstance(value, list):
		for index, item in enumerate(value):
			_validate_json_value(item, f"{label}[{index}]", errors, depth=depth + 1, counter=counter)
		return
	if isinstance(value, dict):
		for item_key, item_value in value.items():
			if not isinstance(item_key, str) or not item_key or len(item_key.encode("utf-8")) > 128 or "\x00" in item_key:
				errors.append(f"{label} contains an invalid object key")
				continue
			_validate_json_value(item_value, f"{label}.{item_key}", errors, depth=depth + 1, counter=counter)
		return
	errors.append(f"{label} contains unsupported value type {type(value).__name__}")


def _validate_event(event: Any, line_number: int, errors: list[str]) -> dict[str, Any] | None:
	label = f"line {line_number}"
	if not isinstance(event, dict):
		errors.append(f"{label} must be a JSON object")
		return None
	missing = EVENT_FIELDS - set(event)
	unknown = set(event) - EVENT_FIELDS
	if missing:
		errors.append(f"{label} is missing fields: {sorted(missing)}")
	if unknown:
		errors.append(f"{label} has unknown fields: {sorted(unknown)}")
	if missing:
		return None
	if event["schema_version"] != SCHEMA_VERSION:
		errors.append(f"{label}.schema_version must be {SCHEMA_VERSION}")
	if not isinstance(event["trace_id"], str) or not TRACE_ID_PATTERN.fullmatch(event["trace_id"]):
		errors.append(f"{label}.trace_id is invalid")
	if not isinstance(event["sequence"], int) or isinstance(event["sequence"], bool) or event["sequence"] < 0:
		errors.append(f"{label}.sequence must be a non-negative integer")
	if not _check_timestamp(event["timestamp"]):
		errors.append(f"{label}.timestamp must be an ISO-8601 timestamp with timezone")
	if not isinstance(event["event"], str) or not EVENT_PATTERN.fullmatch(event["event"]):
		errors.append(f"{label}.event is invalid")
	if not isinstance(event["actor"], str) or not ACTOR_PATTERN.fullmatch(event["actor"]):
		errors.append(f"{label}.actor is invalid")
	if event["side_effect"] not in SIDE_EFFECTS:
		errors.append(f"{label}.side_effect must be one of {sorted(SIDE_EFFECTS)}")
	if not isinstance(event["payload"], dict):
		errors.append(f"{label}.payload must be an object")
	else:
		_validate_json_value(event["payload"], f"{label}.payload", errors)
	for field in ("previous_hash", "hash"):
		if not isinstance(event[field], str) or not HASH_PATTERN.fullmatch(event[field]):
			errors.append(f"{label}.{field} must be a lowercase SHA-256 digest")
	return event


def load_trace(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
	"""Load and validate one bounded, hash-chained trace."""
	errors: list[str] = []
	try:
		raw = _read_bounded_bytes(path)
	except TraceError as exc:
		return [], [str(exc)]
	if not raw:
		return [], ["trace is empty"]
	lines = raw.splitlines()
	if len(lines) > MAX_EVENTS:
		return [], [f"trace exceeds {MAX_EVENTS} events"]
	events: list[dict[str, Any]] = []
	for index, line in enumerate(lines, start=1):
		if len(errors) >= MAX_ERRORS:
			break
		if not line.strip():
			errors.append(f"line {index} is blank")
			continue
		if len(line) > MAX_LINE_BYTES:
			errors.append(f"line {index} exceeds {MAX_LINE_BYTES} bytes")
			continue
		try:
			value = json.loads(
				line.decode("utf-8"),
				object_pairs_hook=unique_object,
				parse_constant=_reject_constant,
			)
		except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError, MemoryError) as exc:
			errors.append(f"could not parse line {index}: {exc}")
			continue
		event = _validate_event(value, index, errors)
		if event is not None:
			events.append(event)
	if errors:
		return events, errors[:MAX_ERRORS]
	trace_id = events[0]["trace_id"]
	previous_hash = GENESIS_HASH
	previous_time: datetime | None = None
	for index, event in enumerate(events):
		line_number = index + 1
		if event["trace_id"] != trace_id:
			errors.append(f"line {line_number}.trace_id does not match the trace")
		if event["sequence"] != index:
			errors.append(f"line {line_number}.sequence must be {index}")
		if event["previous_hash"] != previous_hash:
			errors.append(f"line {line_number}.previous_hash does not match the chain")
		current_time = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
		if previous_time is not None and current_time < previous_time:
			errors.append(f"line {line_number}.timestamp moved backwards")
		previous_time = current_time
		expected_hash = compute_event_hash(event)
		if event["hash"] != expected_hash:
			errors.append(f"line {line_number}.hash does not match canonical event bytes")
		previous_hash = event["hash"]
		if len(errors) >= MAX_ERRORS:
			break
	return events, errors[:MAX_ERRORS]


def require_trace(path: Path) -> list[dict[str, Any]]:
	events, errors = load_trace(path)
	if errors:
		raise TraceError(" | ".join(errors))
	return events


def _safe_summary(payload: dict[str, Any]) -> dict[str, Any]:
	redacted = redact_value(payload)
	summary: dict[str, Any] = {}
	for key in ("case_id", "variant", "role", "model", "tool", "command_id", "action", "path", "status", "reason"):
		if key in redacted:
			value = redacted[key]
			if isinstance(value, str) and len(value.encode("utf-8")) > 512:
				value = value.encode("utf-8")[:512].decode("utf-8", errors="ignore") + "..."
			summary[key] = value
	if not summary:
		summary["payload_keys"] = sorted(redacted)[:32]
	return summary


def build_timeline(events: list[dict[str, Any]], *, limit: int = 200) -> list[dict[str, Any]]:
	return [
		{
			"sequence": event["sequence"],
			"timestamp": event["timestamp"],
			"event": event["event"],
			"actor": event["actor"],
			"side_effect": event["side_effect"],
			"summary": _safe_summary(event["payload"]),
		}
		for event in events[:limit]
	]


def inspect_event(events: list[dict[str, Any]], sequence: int) -> dict[str, Any]:
	if sequence < 0 or sequence >= len(events):
		raise TraceError(f"sequence {sequence} is outside trace range 0..{max(len(events) - 1, 0)}")
	event = copy.deepcopy(events[sequence])
	event["payload"] = redact_value(event["payload"])
	return event


def redact_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
	redacted_events: list[dict[str, Any]] = []
	previous_hash = GENESIS_HASH
	for event in events:
		redacted = copy.deepcopy(event)
		redacted["payload"] = redact_value(redacted["payload"])
		redacted = seal_event(redacted, previous_hash)
		redacted_events.append(redacted)
		previous_hash = redacted["hash"]
	return redacted_events


def _write_new_jsonl(path: Path, events: list[dict[str, Any]]) -> None:
	if path.exists() or path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)()):
		raise TraceError(f"output already exists; choose a new path: {path}")
	parent = path.parent
	if not parent.exists() or not parent.is_dir():
		raise TraceError(f"output parent must be an existing directory: {parent}")
	content = b"".join(_canonical_bytes(event) + b"\n" for event in events)
	if len(content) > MAX_TRACE_BYTES:
		raise TraceError(f"redacted trace exceeds {MAX_TRACE_BYTES} bytes")
	temporary_path: Path | None = None
	try:
		with tempfile.NamedTemporaryFile(prefix=f".{path.name}.", suffix=".tmp", dir=parent, delete=False) as handle:
			temporary_path = Path(handle.name)
			handle.write(content)
			handle.flush()
			os.fsync(handle.fileno())
		os.replace(temporary_path, path)
	except OSError as exc:
		if temporary_path is not None:
			try:
				temporary_path.unlink(missing_ok=True)
			except OSError:
				pass
		raise TraceError(f"could not write redacted trace: {exc}") from exc


def build_replay_plan(events: list[dict[str, Any]], *, limit: int = 1_000) -> dict[str, Any]:
	"""Build a sanitized replay plan without executing any recorded action."""
	plan: list[dict[str, Any]] = []
	for event in events[:limit]:
		item = {
			"sequence": event["sequence"],
			"event": event["event"],
			"side_effect": event["side_effect"],
			"decision": "NOT_EXECUTED",
			"requires_human_before_real_replay": event["side_effect"] in {"reversible", "consequential"},
			"summary": _safe_summary(event["payload"]),
		}
		plan.append(item)
	return {
		"ok": True,
		"dry_run": True,
		"trace_id": events[0]["trace_id"],
		"event_count": len(events),
		"planned_count": len(plan),
		"truncated": len(events) > limit,
		"executed_actions": 0,
		"warning": "Replay is evidence inspection only. No tool call, command, write, network request, or side effect was executed.",
		"plan": plan,
	}


def _bounded_int(value: str, low: int, high: int) -> int:
	try:
		parsed = int(value)
	except ValueError as exc:
		raise argparse.ArgumentTypeError("must be an integer") from exc
	if not low <= parsed <= high:
		raise argparse.ArgumentTypeError(f"must be from {low} to {high}")
	return parsed


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Operate on bounded hash-chained Harness JSONL traces")
	subparsers = parser.add_subparsers(dest="command", required=True)
	for name in ("validate", "timeline", "inspect", "redact", "replay"):
		subparser = subparsers.add_parser(name)
		subparser.add_argument("--trace", required=True, help="Path to the source JSONL trace")
		subparser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
	if "timeline" in subparsers.choices:
		subparsers.choices["timeline"].add_argument("--limit", type=lambda value: _bounded_int(value, 1, 1_000), default=200)
	if "inspect" in subparsers.choices:
		subparsers.choices["inspect"].add_argument("--sequence", type=lambda value: _bounded_int(value, 0, MAX_EVENTS - 1), required=True)
	if "redact" in subparsers.choices:
		subparsers.choices["redact"].add_argument("--output", required=True, help="New JSONL path; existing files are never overwritten")
	if "replay" in subparsers.choices:
		subparsers.choices["replay"].add_argument("--limit", type=lambda value: _bounded_int(value, 1, 1_000), default=1_000)
	return parser.parse_args(argv)


def _print_result(result: dict[str, Any], *, as_json: bool) -> None:
	if as_json:
		print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
		return
	if result.get("ok"):
		print(result.get("message", "Trace operation passed."))
	else:
		print("Trace operation failed:", file=sys.stderr)
		for error in result.get("errors", []):
			print(f"- {error}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
	args = parse_args(argv)
	path = Path(args.trace)
	events, errors = load_trace(path)
	if errors:
		result = {"ok": False, "trace": str(path), "errors": errors}
		_print_result(result, as_json=args.json)
		return 1
	try:
		if args.command == "validate":
			result = {
				"ok": True,
				"trace": str(path),
				"trace_id": events[0]["trace_id"],
				"event_count": len(events),
				"head_hash": events[-1]["hash"],
				"message": f"Trace validation passed: {len(events)} events.",
			}
		elif args.command == "timeline":
			items = build_timeline(events, limit=args.limit)
			result = {
				"ok": True,
				"trace_id": events[0]["trace_id"],
				"event_count": len(events),
				"truncated": len(events) > args.limit,
				"timeline": items,
				"message": f"Timeline contains {len(items)} of {len(events)} events.",
			}
		elif args.command == "inspect":
			result = {
				"ok": True,
				"trace_id": events[0]["trace_id"],
				"event": inspect_event(events, args.sequence),
				"message": f"Inspected trace event {args.sequence} with redaction.",
			}
		elif args.command == "redact":
			output = Path(args.output)
			try:
				if path.resolve(strict=True) == output.resolve(strict=False):
					raise TraceError("redacted output must differ from the source trace")
			except OSError as exc:
				raise TraceError(f"could not resolve trace paths: {exc}") from exc
			redacted_events = redact_events(events)
			_write_new_jsonl(output, redacted_events)
			result = {
				"ok": True,
				"source_trace": str(path),
				"output_trace": str(output),
				"trace_id": events[0]["trace_id"],
				"event_count": len(redacted_events),
				"head_hash": redacted_events[-1]["hash"],
				"message": f"Wrote a redacted, re-chained trace to {output}.",
			}
		else:
			result = build_replay_plan(events, limit=args.limit)
	except TraceError as exc:
		result = {"ok": False, "trace": str(path), "errors": [str(exc)]}
		_print_result(result, as_json=args.json)
		return 1
	_print_result(result, as_json=args.json)
	if not args.json and args.command in {"timeline", "inspect", "replay"}:
		print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
