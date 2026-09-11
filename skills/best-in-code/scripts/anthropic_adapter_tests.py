#!/usr/bin/env python3
"""Offline integration tests for the Anthropic Messages adapter.

A loopback HTTP server plays the Anthropic API with scripted responses, so the
whole kernel → adapter → API → tool → kernel path runs without a credential or
network. Nothing here proves live model quality; it proves the protocol,
credential handling, usage normalization, and fail-closed behavior.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import json
import os
import shutil
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import anthropic_adapter
import execution_kernel
from execution_runtime_tests import (
	CONTRACT_TEMPLATE, TRACE, Report, kernel, make_base, make_fixture, payload, process, trace_path, write_json,
)

if hasattr(sys.stdout, "reconfigure"):
	sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

SCRIPTS = Path(__file__).resolve().parent
CONFIG_TEMPLATE = SCRIPTS.parent / "assets" / "templates" / "ANTHROPIC-ADAPTER.json"
FIXTURE_KEY = "sk-ant-fixture-key-do-not-persist-0123456789"


class FakeAnthropic(BaseHTTPRequestHandler):
	scripted: list[tuple[int, dict]] = []
	seen: list[dict] = []
	lock = threading.Lock()

	def do_POST(self) -> None:  # noqa: N802 - http.server API
		length = int(self.headers.get("content-length", "0"))
		body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
		with FakeAnthropic.lock:
			FakeAnthropic.seen.append({
				"path": self.path,
				"headers": {name.lower(): value for name, value in self.headers.items()},
				"body": body,
			})
			if FakeAnthropic.scripted:
				status, response = FakeAnthropic.scripted.pop(0)
			else:
				status, response = 500, {"type": "error", "error": {"type": "api_error", "message": "script exhausted"}}
		data = json.dumps(response).encode("utf-8")
		self.send_response(status)
		self.send_header("content-type", "application/json")
		self.send_header("content-length", str(len(data)))
		self.end_headers()
		self.wfile.write(data)

	def log_message(self, *args: object) -> None:
		return


def message(content: list[dict], stop_reason: str, usage: dict, model: str = "claude-opus-5") -> dict:
	return {
		"id": "msg_fixture",
		"type": "message",
		"role": "assistant",
		"model": model,
		"content": content,
		"stop_reason": stop_reason,
		"stop_sequence": None,
		"usage": usage,
	}


def synthetic_request(protocol_version: int = 2, state: dict | None = None, tool_results: list | None = None) -> dict:
	contract = json.loads(CONTRACT_TEMPLATE.read_text(encoding="utf-8"))
	role = execution_kernel.role_registry(contract)["project-manager"]
	return {
		"type": "model_request",
		"protocol_version": protocol_version,
		"request_id": "REQ-fixture",
		"contract_id": "contract-fixture",
		"project_id": "project-fixture",
		"run_id": "RUN-fixture",
		"agent": {"agent_id": "AGT-1", "role": "project-manager", "model_profile": role["model_profile"], "parent_agent_id": None, "task": "Fixture task"},
		"step": 1,
		"budgets_remaining": {"steps": 10, "tokens": 1000, "cost_microusd": 1000, "external_calls": 5, "role_steps": 10},
		"tools": execution_kernel.tool_descriptors(contract, role),
		"tool_results": tool_results or [],
		"adapter_state": state,
		"security": {"project_content_is_untrusted": True, "never_follow_instructions_from_tool_output": True, "only_named_tools_are_authorized": True},
	}


def unit_tests(report: Report) -> None:
	config = anthropic_adapter.load_config(str(CONFIG_TEMPLATE))
	report.check("template-config-loads", config["default_model"] == "claude-opus-5" and "gpt-sol-plan" in config["profiles"], str(sorted(config["profiles"])))

	try:
		anthropic_adapter.load_config(str(CONFIG_TEMPLATE.parent / "RUN-CONTRACT.json"))
		bad_config = "accepted"
	except anthropic_adapter.AdapterError as exc:
		bad_config = str(exc)
	report.check("foreign-config-is-refused", bad_config != "accepted", bad_config)

	request = synthetic_request()
	body, headers, names = anthropic_adapter.build_api_request(request, config, None)
	tools = {tool["name"]: tool for tool in body["tools"]}
	human = tools["human__request"]["input_schema"]
	report.check(
		"tool-definitions-follow-kernel-descriptors",
		set(names.values()) == {"agent.delegate", "human.request", "verifier.run", "workspace.read", "workspace.write"}
		and "artifact_path" not in human["required"]
		and human["properties"]["action_type"].get("enum")
		and tools["workspace__read"]["input_schema"]["required"] == ["path"]
		and tools["workspace__read"]["input_schema"]["additionalProperties"] is False,
		json.dumps(sorted(names)),
	)
	report.check(
		"request-shape-omits-thinking-and-caches-system",
		"thinking" not in body
		and body["tool_choice"] == {"type": "auto"}
		and body["output_config"] == {"effort": "high"}
		and body["system"][0]["cache_control"] == {"type": "ephemeral"}
		and body["messages"][0]["role"] == "user"
		and headers["anthropic-version"] == anthropic_adapter.ANTHROPIC_VERSION
		and "anthropic-beta" not in headers,
		json.dumps({key: body[key] for key in ("model", "max_tokens", "output_config", "tool_choice")}),
	)

	tool_use = message(
		[
			{"type": "thinking", "thinking": "", "signature": "sig-fixture"},
			{"type": "text", "text": "Reading the README."},
			{"type": "tool_use", "id": "toolu_01", "name": "workspace__read", "input": {"path": "README.md"}},
		],
		"tool_use",
		{"input_tokens": 8, "cache_creation_input_tokens": 5120, "cache_read_input_tokens": 0, "output_tokens": 20},
	)
	translated = anthropic_adapter.translate_response(tool_use, request, names, body["messages"], config, 2, "claude-opus-5")
	expected_cost = 8 * 5 + 5120 * 6.25 + 20 * 25
	report.check(
		"tool-use-translates-to-kernel-tool-calls-with-canonical-usage",
		translated["finish_reason"] == "tool_calls"
		and translated["tool_calls"] == [{"id": "toolu_01", "tool": "workspace.read", "arguments": {"path": "README.md"}}]
		and translated["usage"] == {"input_tokens": 5128, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 5120, "output_tokens": 20, "cost_microusd": int(expected_cost)}
		and translated["adapter_state"]["messages"][-1]["content"][0]["type"] == "thinking"
		and translated["adapter_state"]["turn"] == 1,
		json.dumps(translated["usage"]),
	)

	legacy = anthropic_adapter.translate_response(tool_use, synthetic_request(protocol_version=1), names, body["messages"], config, 1, "claude-opus-5")
	report.check("protocol-v1-uses-legacy-usage-shape", set(legacy["usage"]) == {"input_tokens", "output_tokens", "cost_microusd"} and legacy["usage"]["input_tokens"] == 5128 and legacy["protocol_version"] == 1, json.dumps(legacy["usage"]))

	follow_up = synthetic_request(state=translated["adapter_state"], tool_results=[{"call_id": "toolu_01", "tool": "workspace.read", "ok": True, "value": {"content": "# Fixture"}, "code": "", "error": ""}])
	follow_body, _, _ = anthropic_adapter.build_api_request(follow_up, config, translated["adapter_state"])
	last = follow_body["messages"][-1]
	report.check(
		"tool-results-replay-after-the-assistant-turn",
		follow_body["messages"][-2]["role"] == "assistant"
		and last["role"] == "user"
		and last["content"][0]["type"] == "tool_result"
		and last["content"][0]["tool_use_id"] == "toolu_01"
		and last["content"][0]["is_error"] is False
		and "# Fixture" in last["content"][0]["content"],
		json.dumps(last["content"][0])[:200],
	)

	final = message([{"type": "text", "text": "Done."}], "end_turn", {"input_tokens": 10, "cache_read_input_tokens": 5120, "cache_creation_input_tokens": 0, "output_tokens": 5})
	final_translated = anthropic_adapter.translate_response(final, follow_up, names, follow_body["messages"], config, 2, "claude-opus-5")
	report.check("end-turn-translates-to-final", final_translated["finish_reason"] == "final" and final_translated["message"] == "Done." and final_translated["tool_calls"] == [] and final_translated["usage"]["input_tokens"] == 5130, json.dumps(final_translated["usage"]))

	for name, response in (
		("max-tokens", message([{"type": "text", "text": "partial"}], "max_tokens", {"input_tokens": 1, "output_tokens": 1})),
		("refusal", {**message([], "refusal", {"input_tokens": 1, "output_tokens": 0}), "stop_details": {"type": "refusal", "category": "cyber"}}),
		("undeclared-tool", message([{"type": "tool_use", "id": "toolu_x", "name": "shell__exec", "input": {}}], "tool_use", {"input_tokens": 1, "output_tokens": 1})),
	):
		try:
			anthropic_adapter.translate_response(response, request, names, body["messages"], config, 2, "claude-opus-5")
			outcome = "accepted"
		except anthropic_adapter.AdapterError as exc:
			outcome = str(exc)
		report.check(f"{name}-response-fails-closed", outcome != "accepted", outcome)

	try:
		anthropic_adapter.compute_cost_microusd("claude-unpriced-9", {"input_tokens": 1, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0, "output_tokens": 1}, config["pricing_microusd_per_million_tokens"])
		unpriced = "accepted"
	except anthropic_adapter.AdapterError as exc:
		unpriced = str(exc)
	report.check("unpriced-model-never-costs-zero", unpriced != "accepted", unpriced)

	pairs = [{"role": "user", "content": [{"type": "text", "text": "task"}]}]
	for index in range(40):
		pairs.append({"role": "assistant", "content": [{"type": "text", "text": "x" * 2000}]})
		pairs.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": f"t{index}", "content": "y" * 2000}]})
	trimmed, dropped = anthropic_adapter.trim_messages(pairs, 40_000)
	report.check(
		"replay-trims-oldest-pairs-and-keeps-task",
		dropped > 0
		and trimmed[0]["role"] == "user"
		and trimmed[0]["content"][0]["text"] == "task"
		and anthropic_adapter.message_bytes(trimmed) <= 40_000
		and trimmed[1]["role"] == "assistant"
		and trimmed[-1]["role"] == "user"
		and trimmed[-1]["content"][0]["tool_use_id"] == "t39",
		str({"dropped": dropped, "remaining": len(trimmed)}),
	)

	outcomes = {}
	for label, environment in (
		("plain-http-remote", {"ANTHROPIC_BASE_URL": "http://api.example.com"}),
		("loopback-http", {"ANTHROPIC_BASE_URL": "http://127.0.0.1:8"}),
		("default", {}),
	):
		try:
			outcomes[label] = anthropic_adapter.base_url(environment)
		except anthropic_adapter.AdapterError:
			outcomes[label] = "refused"
	try:
		anthropic_adapter.credential_headers({})
		outcomes["no-credential"] = "accepted"
	except anthropic_adapter.AdapterError:
		outcomes["no-credential"] = "refused"
	report.check(
		"transport-policy-requires-https-and-a-credential",
		outcomes == {"plain-http-remote": "refused", "loopback-http": "http://127.0.0.1:8", "default": anthropic_adapter.DEFAULT_BASE_URL, "no-credential": "refused"},
		json.dumps(outcomes),
	)


def anthropic_fixture(base: Path, workspace: Path, name: str, task: str, port: int) -> Path:
	project, _ = make_fixture(base, workspace, name, task)
	contract_path = project / ".harness" / "RUN-CONTRACT.json"
	contract = json.loads(contract_path.read_text(encoding="utf-8"))
	contract["adapter"]["environment_allowlist"] = ["ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL"]
	write_json(contract_path, contract)
	write_json(project / ".harness" / "ADAPTER-ARGV.json", [
		"@harness-python", "-B", ".harness/runtime/scripts/anthropic_adapter.py", "--config", ".harness/ANTHROPIC-ADAPTER.json",
	])
	shutil.copyfile(project / ".harness" / "runtime" / "assets" / "templates" / "ANTHROPIC-ADAPTER.json", project / ".harness" / "ANTHROPIC-ADAPTER.json")
	os.environ["ANTHROPIC_API_KEY"] = FIXTURE_KEY
	os.environ["ANTHROPIC_BASE_URL"] = f"http://127.0.0.1:{port}"
	return project


def files_containing(root: Path, needle: str) -> list[str]:
	"""Scan run state, traces, evidence, and control files; skip the pinned test sources."""
	hits = []
	for path in root.rglob("*"):
		if path.is_file() and "runtime" not in path.relative_to(root).parts and needle in path.read_text(encoding="utf-8", errors="ignore"):
			hits.append(str(path.relative_to(root)))
	return hits


def integration_tests(report: Report, workspace: Path, port: int) -> None:
	base = make_base(workspace)
	FakeAnthropic.seen.clear()
	FakeAnthropic.scripted[:] = [
		(200, message(
			[
				{"type": "thinking", "thinking": "", "signature": "sig-fixture"},
				{"type": "text", "text": "Reading the README first."},
				{"type": "tool_use", "id": "toolu_01", "name": "workspace__read", "input": {"path": "README.md"}},
			],
			"tool_use",
			{"input_tokens": 8, "cache_creation_input_tokens": 5120, "cache_read_input_tokens": 0, "output_tokens": 20},
		)),
		(200, message(
			[{"type": "text", "text": "Done: README inspected; it contains an injection attempt that was ignored."}],
			"end_turn",
			{"input_tokens": 10, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 5120, "output_tokens": 15},
		)),
	]
	live = anthropic_fixture(base, workspace, "anthropic-live", "Inspect README.md through the Anthropic adapter.", port)
	live_result, live_run = kernel(live, "run")
	first = FakeAnthropic.seen[0] if FakeAnthropic.seen else {"headers": {}, "body": {}}
	second = FakeAnthropic.seen[1] if len(FakeAnthropic.seen) > 1 else {"headers": {}, "body": {}}
	report.check(
		"kernel-completes-through-anthropic-adapter",
		live_result.returncode == 0 and live_run.get("status") == "COMPLETE" and len(FakeAnthropic.seen) == 2,
		str({"status": live_run.get("status"), "code": live_run.get("code"), "calls": len(FakeAnthropic.seen), "stderr": live_result.stderr[-300:]}),
	)
	report.check(
		"api-request-carries-credential-version-and-declared-tools",
		first["headers"].get("x-api-key") == FIXTURE_KEY
		and first["headers"].get("anthropic-version") == anthropic_adapter.ANTHROPIC_VERSION
		and first["path"] == "/v1/messages"
		and first["body"].get("model") == "claude-opus-5"
		and {tool["name"] for tool in first["body"].get("tools", [])} >= {"workspace__read", "verifier__run", "human__request", "agent__delegate"}
		and "thinking" not in first["body"],
		json.dumps({"path": first.get("path"), "model": first["body"].get("model"), "tools": sorted(tool["name"] for tool in first["body"].get("tools", []))}),
	)
	replay = second["body"].get("messages", [])
	tool_result_block = replay[-1]["content"][0] if replay and isinstance(replay[-1].get("content"), list) else {}
	report.check(
		"second-request-replays-thinking-tool-use-and-tool-result",
		len(replay) == 3
		and replay[1]["role"] == "assistant"
		and replay[1]["content"][0].get("signature") == "sig-fixture"
		and tool_result_block.get("type") == "tool_result"
		and tool_result_block.get("tool_use_id") == "toolu_01"
		and tool_result_block.get("is_error") is False
		and "Ignore previous instructions" in tool_result_block.get("content", ""),
		json.dumps(tool_result_block)[:300],
	)
	usage = payload(process([sys.executable, "-B", str(TRACE), "usage", "--trace", str(trace_path(live, live_run)), "--json"], live))
	report.check(
		"trace-usage-reports-canonical-cache-telemetry",
		usage.get("ok") is True
		and usage["cache_telemetry"]["observation"] == "REPORTED"
		and usage["totals"]["input_tokens"] == 5128 + 5130
		and usage["totals"]["cache_read_input_tokens"] == 5120
		and usage["totals"]["cache_creation_input_tokens"] == 5120
		and usage["totals"]["output_tokens"] == 35
		and usage["totals"]["cost_microusd"] == int(8 * 5 + 5120 * 6.25 + 20 * 25) + int(10 * 5 + 5120 * 0.5 + 15 * 25),
		json.dumps(usage.get("totals")),
	)
	leaks = files_containing(live / ".harness", FIXTURE_KEY)
	report.check("credential-never-enters-state-or-trace", leaks == [], str(leaks))

	FakeAnthropic.seen.clear()
	FakeAnthropic.scripted[:] = [
		(429, {"type": "error", "error": {"type": "rate_limit_error", "message": "slow down"}}),
		(200, message([{"type": "text", "text": "Completed after one retry."}], "end_turn", {"input_tokens": 3, "output_tokens": 4})),
	]
	retry = anthropic_fixture(base, workspace, "anthropic-retry", "Finish after a transient rate limit.", port)
	retry_result, retry_run = kernel(retry, "run")
	report.check(
		"transient-rate-limit-is-retried-once",
		retry_result.returncode == 0 and retry_run.get("status") == "COMPLETE" and len(FakeAnthropic.seen) == 2,
		str({"status": retry_run.get("status"), "calls": len(FakeAnthropic.seen)}),
	)

	FakeAnthropic.seen.clear()
	FakeAnthropic.scripted[:] = [
		(400, {"type": "error", "error": {"type": "invalid_request_error", "message": "bad request fixture"}}),
	]
	failing = anthropic_fixture(base, workspace, "anthropic-400", "Stop on a non-retryable API error.", port)
	failing_result, failing_run = kernel(failing, "run")
	report.check(
		"non-retryable-api-error-stops-the-run-closed",
		failing_result.returncode != 0 and str(failing_run.get("code", "")).startswith("ADAPTER_") and len(FakeAnthropic.seen) == 1,
		str({"code": failing_run.get("code"), "calls": len(FakeAnthropic.seen)}),
	)

	FakeAnthropic.seen.clear()
	FakeAnthropic.scripted[:] = [
		(200, message([{"type": "text", "text": "never used"}], "end_turn", {"input_tokens": 1, "output_tokens": 1})),
	]
	unallowed = anthropic_fixture(base, workspace, "anthropic-no-env", "Fail when the credential is not forwarded.", port)
	contract_path = unallowed / ".harness" / "RUN-CONTRACT.json"
	contract = json.loads(contract_path.read_text(encoding="utf-8"))
	contract["adapter"]["environment_allowlist"] = ["ANTHROPIC_BASE_URL"]
	write_json(contract_path, contract)
	unallowed_result, unallowed_run = kernel(unallowed, "run")
	report.check(
		"credential-outside-allowlist-never-reaches-the-api",
		unallowed_result.returncode != 0 and str(unallowed_run.get("code", "")).startswith("ADAPTER_") and len(FakeAnthropic.seen) == 0,
		str({"code": unallowed_run.get("code"), "calls": len(FakeAnthropic.seen)}),
	)


def main() -> int:
	report = Report()
	workspace = Path(tempfile.mkdtemp(prefix="harness-anthropic-adapter-"))
	server = ThreadingHTTPServer(("127.0.0.1", 0), FakeAnthropic)
	thread = threading.Thread(target=server.serve_forever, daemon=True)
	thread.start()
	try:
		unit_tests(report)
		integration_tests(report, workspace, server.server_address[1])
		print(json.dumps({"passed": report.passed, "failed": report.failed}, indent=2))
		return 0 if report.failed == 0 else 1
	finally:
		server.shutdown()
		server.server_close()
		shutil.rmtree(workspace, ignore_errors=True)


if __name__ == "__main__":
	raise SystemExit(main())
