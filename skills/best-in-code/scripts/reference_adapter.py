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


def response(request: dict[str, Any]) -> dict[str, Any]:
	state = request.get("adapter_state")
	turn = state.get("turn", 0) if isinstance(state, dict) else 0
	agent = request.get("agent", {})
	role = str(agent.get("role", "agent"))
	task = str(agent.get("task", ""))
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
		"protocol_version": 1,
		"request_id": request.get("request_id"),
		"finish_reason": finish_reason,
		"message": message,
		"tool_calls": tool_calls,
		"adapter_state": {"turn": turn + 1},
		"usage": {"input_tokens": 1, "output_tokens": 1, "cost_microusd": 0},
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
