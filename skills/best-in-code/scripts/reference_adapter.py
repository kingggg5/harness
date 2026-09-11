#!/usr/bin/env python3
"""Deterministic JSONL adapter for protocol demos and smoke tests.

This is deliberately not an AI model. Replace its argv with a provider adapter
that maps `agent.model_profile` to the desired model while preserving the same
bounded request/response contract.
"""

from __future__ import annotations

import json
import sys
from typing import Any

sys.dont_write_bytecode = True

LEGACY_PROTOCOL_VERSION = 1
CURRENT_PROTOCOL_VERSION = 2
SUPPORTED_PROTOCOL_VERSIONS = {LEGACY_PROTOCOL_VERSION, CURRENT_PROTOCOL_VERSION}


def canonical_cache_usage(
	*,
	uncached_input_tokens: int,
	cache_read_input_tokens: int,
	cache_creation_input_tokens: int,
	output_tokens: int,
	cost_microusd: int,
) -> dict[str, int]:
	"""Map provider parts into Harness's canonical total-input receipt.

	For example, an Anthropic-style raw receipt with 8 uncached input tokens and
	5,120 cache-creation tokens becomes one canonical input total of 5,128.
	"""
	return {
		"input_tokens": uncached_input_tokens + cache_read_input_tokens + cache_creation_input_tokens,
		"cache_read_input_tokens": cache_read_input_tokens,
		"cache_creation_input_tokens": cache_creation_input_tokens,
		"output_tokens": output_tokens,
		"cost_microusd": cost_microusd,
	}


def usage_for_task(task: str, *, cache_telemetry_supported: bool) -> dict[str, int]:
	"""Emit deterministic protocol shapes; ordinary demo runs stay telemetry-free."""
	legacy = {"input_tokens": 1, "output_tokens": 1, "cost_microusd": 0}
	if "legacy-usage-demo" in task:
		return legacy
	if "normalized-cache-usage-demo" in task and cache_telemetry_supported:
		return canonical_cache_usage(
			uncached_input_tokens=8,
			cache_read_input_tokens=0,
			cache_creation_input_tokens=5_120,
			output_tokens=1,
			cost_microusd=0,
		)
	if "bad-cache-partial-demo" in task and cache_telemetry_supported:
		return {**legacy, "cache_read_input_tokens": 0}
	if "bad-cache-over-input-demo" in task and cache_telemetry_supported:
		return {
			**legacy,
			"cache_read_input_tokens": 1,
			"cache_creation_input_tokens": 1,
		}
	if "bad-v1-cache-telemetry-demo" in task and cache_telemetry_supported:
		return canonical_cache_usage(
			uncached_input_tokens=1,
			cache_read_input_tokens=0,
			cache_creation_input_tokens=1,
			output_tokens=1,
			cost_microusd=0,
		)
	if "max-usage-overshoot-demo" in task:
		return {
			"input_tokens": 10**15,
			"output_tokens": 10**15,
			"cost_microusd": 10**15,
		}
	return legacy


def response(request: dict[str, Any]) -> dict[str, Any]:
	requested_protocol = request.get("protocol_version")
	protocol_version = (
		requested_protocol
		if isinstance(requested_protocol, int)
		and not isinstance(requested_protocol, bool)
		and requested_protocol in SUPPORTED_PROTOCOL_VERSIONS
		else LEGACY_PROTOCOL_VERSION
	)
	state = request.get("adapter_state")
	turn = state.get("turn", 0) if isinstance(state, dict) else 0
	agent = request.get("agent", {})
	role = str(agent.get("role", "agent"))
	task = str(agent.get("task", ""))
	# Fixture-only compatibility probes. A strict v1 adapter rejects v2 requests
	# rather than silently guessing their semantics; the kernel must therefore
	# select v1 from a legacy contract before the adapter receives a request.
	if "strict-v1-adapter-demo" in task and requested_protocol != LEGACY_PROTOCOL_VERSION:
		return {"adapter_error": "strict v1 adapter refused a non-v1 request"}
	if "legacy-response-v1-demo" in task or "bad-v1-cache-telemetry-demo" in task:
		protocol_version = LEGACY_PROTOCOL_VERSION
	tool_results = request.get("tool_results", [])
	tool_calls: list[dict[str, Any]] = []
	message = ""
	finish_reason = "final"
	if turn == 0 and "delegate-demo" in task and role == "project-manager":
		finish_reason = "tool_calls"
		tool_calls = [{
			"id": "delegate-planner",
			"tool": "agent.delegate",
			"arguments": {"role": "planner", "task": "Return a concise verified plan."},
		}]
	elif turn == 0 and "verifier-demo" in task:
		finish_reason = "tool_calls"
		tool_calls = [{
			"id": "run-verifier",
			"tool": "verifier.run",
			"arguments": {"command_id": "test"},
		}]
	elif turn == 0 and "approval-demo" in task:
		finish_reason = "tool_calls"
		tool_calls = [{
			"id": "request-human",
			"tool": "human.request",
			"arguments": {
				"action_id": "demo-acceptance",
				"action_type": "other",
				"question": "Approve the deterministic demo?",
				"artifact_path": "",
			},
		}]
	elif turn == 0 and "read-demo" in task:
		finish_reason = "tool_calls"
		tool_calls = [{
			"id": "read-demo-file",
			"tool": "workspace.read",
			"arguments": {"path": "README.md"},
		}]
	else:
		suffix = f" Received {len(tool_results)} trusted tool result(s)." if tool_results else ""
		message = f"Deterministic {role} adapter completed the bounded task.{suffix}"
	return {
		"type": "model_response",
		"protocol_version": protocol_version,
		"request_id": request.get("request_id"),
		"finish_reason": finish_reason,
		"message": message,
		"tool_calls": tool_calls,
		"adapter_state": {"turn": turn + 1},
		"usage": usage_for_task(
			task,
			cache_telemetry_supported=(
				protocol_version >= CURRENT_PROTOCOL_VERSION
				or "bad-v1-cache-telemetry-demo" in task
			),
		),
	}


def main() -> int:
	for line in sys.stdin:
		try:
			request = json.loads(line)
			print(json.dumps(response(request), ensure_ascii=False, sort_keys=True, separators=(",", ":")), flush=True)
		except (json.JSONDecodeError, TypeError, ValueError) as exc:
			print(json.dumps({"adapter_error": str(exc)}, ensure_ascii=False), flush=True)
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
