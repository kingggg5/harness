# Executable agent graph

Use this optional runtime when a reviewed Harness plan must become a durable, resumable multi-agent execution rather than a sequence managed only by the current chat host. Skip it for quick work, read-only review, or when the host already provides stronger trusted execution controls.

The runtime treats the model as an untrusted decision component. A model can return text or select a named tool, but it cannot invent a command, path scope, environment variable, permission, approval, child role, budget, or model route. Those come only from the human-reviewed `RUN-CONTRACT.json`.

## What runs

The default contract contains these logical roles:

- Project Manager: root owner and graph orchestrator.
- Business Analyst: conditional requirements pass.
- Planner, Researcher, Designer, Frontend, Backend, and Tester/Reviewer/QA.

Each role has a `model_profile`. A provider adapter maps that portable profile to an available model. The template suggests Sol-class reasoning for orchestration/planning/review, Terra-class balanced models for implementation/design, and Luna-class fast models for bounded research or analysis. These are routing hints, not hard dependencies; user-pinned models and verified provider availability win.

Execution is deterministic around the model:

1. The kernel verifies Project ID, Run ID, active Harness state, pinned-runtime digest, contract schema, tool scopes, delegation graph, budgets, and adapter argv.
2. It commits a pending model-call receipt before sending a bounded JSONL request.
3. It validates the exact response schema and usage counters.
4. Tool calls pass through capability, scope, input, output, timeout, approval, and idempotency checks.
5. Child roles receive only a subset of both the declared child capability set and the parent's actual capabilities.
6. Every transition enters a canonical SHA-256 hash-chained trace.

Only one agent owns execution at a time in this reference kernel. Delegation is graph-shaped and resumable, but not concurrent. Use the existing isolated graph/worktree runtime when parallel writers are worth the added coordination cost.

## Prepare one run

Initialize Harness first, then copy the reviewed templates from the pinned runtime:

```bash
cp .harness/runtime/assets/templates/RUN-CONTRACT.json .harness/RUN-CONTRACT.json
cp .harness/runtime/assets/templates/ADAPTER-ARGV.json .harness/ADAPTER-ARGV.json
```

On PowerShell, use `Copy-Item` for the same two files. Edit the copy, not the pinned runtime:

- Set `project_id` to `.harness/IDENTITY.json`.
- Set `run_id` to the active `.harness/STATE.json` run.
- Write one bounded task and acceptance target.
- Replace example verifier argv with exact project commands.
- Narrow read/write scopes and remove unused tools or roles.
- Map model profiles in the real provider adapter.

The bundled adapter is deterministic and intentionally contains no AI provider. It proves the protocol and supports smoke tests. Production use supplies a separately reviewed adapter argv; the adapter reads one JSON request from stdin and writes one JSON response line to stdout.

`@harness-python` is the only portable executable token: the kernel resolves it to the exact Python interpreter that launched the run. Every other argv executable must be an absolute regular-file path. Bare `python`, `python3`, `node`, or any other PATH command is refused, so a project directory or changed PATH cannot silently substitute the reviewed program. Keep `-B` for Python adapters; the kernel also sets `PYTHONDONTWRITEBYTECODE=1` for child processes.

## Commands

```bash
harness run-validate --project . --contract .harness/RUN-CONTRACT.json --adapter-argv-file .harness/ADAPTER-ARGV.json --json
harness run --project . --contract .harness/RUN-CONTRACT.json --adapter-argv-file .harness/ADAPTER-ARGV.json --json
harness run-status --project . --contract .harness/RUN-CONTRACT.json --json
harness run-approve --project . --contract .harness/RUN-CONTRACT.json --request-id APR-... --decision approved --actor your-name --json
harness run-cancel --project . --contract .harness/RUN-CONTRACT.json --reason "Operator stopped the run" --json
harness run-trace-verify --project . --contract .harness/RUN-CONTRACT.json --json
```

`WAITING_APPROVAL` is a successful pause. Review the question, action ID, artifact digest, request digest, and expiry before deciding. The receipt is immutable and bound to the exact Project/Run/agent/tool/action tuple; changing its bytes invalidates the run. Kernel completion is technical completion only. The normal Harness Acceptance Gate still belongs to the human.

## Crash and cancellation semantics

- A model call is recorded before dispatch. If the process dies while it is outstanding, resume stops with `INDETERMINATE_EXTERNAL_CALL`; the kernel never guesses whether a billed call completed.
- An atomic workspace write is recorded before mutation. Resume accepts it only when the target bytes match the expected artifact digest exactly.
- An interrupted registered verifier is treated as an indeterminate side effect and fails closed.
- Cancellation is a project/run/contract-bound marker checked between transitions and while waiting on an adapter or verifier. It never force-cleans files, kills unrelated processes, rolls back Git, publishes, or deploys.

## Adapter protocol

Requests contain the exact project/run/contract identity, active agent and model profile, task, step, remaining budgets, capability descriptors, prior trusted tool results, bounded adapter state, and a security boundary declaring project content untrusted.

Responses must contain exactly:

```json
{
	"type": "model_response",
	"protocol_version": 1,
	"request_id": "REQ-...",
	"finish_reason": "tool_calls",
	"message": "",
	"tool_calls": [
		{
			"id": "stable-call-id",
			"tool": "workspace.read",
			"arguments": {
				"path": "src/example.ts"
			}
		}
	],
	"adapter_state": {},
	"usage": {
		"input_tokens": 0,
		"output_tokens": 0,
		"cost_microusd": 0
	}
}
```

`finish_reason: final` requires non-empty `message` and no tool calls. The adapter must use `request_id` as its provider-side idempotency key when the provider supports one. Raw shell strings and free-form environment changes are never part of this protocol.
