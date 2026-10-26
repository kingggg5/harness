# Executable agent graph

Use this optional runtime when a reviewed Harness plan must become a durable, resumable multi-agent execution rather than a sequence managed only by the current chat host. Skip it for quick work, read-only review, or when the host already provides stronger trusted execution controls.

The runtime treats the model as an untrusted decision component. A model can return text or select a named tool, but it cannot invent a command, path scope, environment variable, permission, approval, child role, budget, or model route. Those come only from the human-reviewed `RUN-CONTRACT.json`.

## What runs

The default contract contains these logical roles:

- Project Manager: root owner and graph orchestrator.
- Business Analyst: conditional requirements pass.
- Planner, Researcher, Designer, Frontend, Backend, and Tester/Reviewer/QA.

Each role has a portable `model_profile` that the provider adapter maps to an available model. The template's Sol/Terra/Luna-class profile names are routing hints that do not authorize model switching: by default bind every profile to the task's fixed model and effort; distinct role bindings or a cheaper model require an explicitly approved model plan recorded in `WORKFLOW.md`. User-pinned models and verified provider availability win. The adapter must enforce that binding and report its actual selection; the kernel validates the contract but cannot attest which provider model the adapter used.

Execution is deterministic around the model:

1. The kernel verifies Project ID, Run ID, active Harness state, pinned-runtime digest, contract schema, tool scopes, delegation graph, budgets, and adapter argv.
2. It commits a pending model-call receipt before sending a bounded JSONL request.
3. It validates the exact response schema and normalized provider usage counters.
4. Tool calls pass through capability, scope, input, output, timeout, approval, and idempotency checks.
5. Child roles receive only a subset of both the declared child capability set and the parent's actual capabilities.
6. Every transition enters a canonical SHA-256 hash-chained trace.

Only one agent owns execution at a time in this reference kernel. Delegation is graph-shaped and resumable, but not concurrent. Use the existing isolated graph/worktree runtime when parallel writers are worth the added coordination cost.

This kernel executes pending tool calls synchronously and does not accept live user steering during a run. For a design that introduces long-running background tools, resumable operation IDs, cancellation or user input while work continues, read [async-operation-runtime.md](async-operation-runtime.md) before changing the execution schema. Do not model the current task-graph ledger as an async tool executor.

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

## Verifier isolation policy

Run-contract schemas v2 and v3 declare `"verifier_isolation": "required"` or `"best-effort"`. The template defaults to `required`. If the strict backend cannot be established, the verifier does not run and the call returns `EXEC_ISOLATION_UNAVAILABLE` with the reason.

| Host | `required` backend | Teardown guarantee |
|---|---|---|
| Windows | Verifier starts suspended, is bound to a no-breakaway Job Object, and resumes only after binding succeeds | Job teardown kills the full job tree |
| Linux | Verifier runs as PID 1 of a fresh user + PID namespace via util-linux `unshare --user --pid --fork --kill-child --map-current-user`; the kernel probes once per process that the launcher yields PID 1 with the caller's uid/gid | Killing the launcher's group ends the namespace init, and the kernel SIGKILLs every process in it, including a `setsid()` descendant |
| macOS and other POSIX | None bundled | Fails closed; supply an operator-managed sandbox that wraps the verifier argv |

Reasons the Linux probe fails closed include a missing `unshare`, util-linux older than 2.38 (no `--map-current-user`), disabled unprivileged user namespaces, an AppArmor or seccomp profile that blocks `unshare` (Docker's default profile does), or a kernel without PID namespaces. Successful verifier results record `"isolation": "linux-pid-namespace"`, `"windows-job-object"`, or `"posix-process-group"` so evidence states which primitive actually ran.

`best-effort` is retained for legacy v1 contracts and an explicit schema-v2 operator choice: it cleans the original verifier process group, but a hostile descendant can create a new session/process group (for example with `setsid()`). Do not use `best-effort` to run project-controlled or hostile code.

## Anthropic adapter

`anthropic_adapter.py` is the bundled real-provider adapter. It uses only the Python standard library, so the pinned runtime copy runs without installing packages.

```bash
cp .harness/runtime/assets/templates/ANTHROPIC-ADAPTER.json .harness/ANTHROPIC-ADAPTER.json
```

- `ADAPTER-ARGV.json`: `["@harness-python", "-B", ".harness/runtime/scripts/anthropic_adapter.py", "--config", ".harness/ANTHROPIC-ADAPTER.json"]`.
- `RUN-CONTRACT.json`: add `"ANTHROPIC_API_KEY"` (or `"ANTHROPIC_AUTH_TOKEN"`, optionally `"ANTHROPIC_BASE_URL"`) to `adapter.environment_allowlist`. The credential is read from the process environment only; it is never accepted from the config, the contract, or project content, and the adapter suite proves it does not enter state, evidence, or the trace.
- The config's `profiles` bind each `model_profile` to `{model, effort}`; unmapped profiles use `default_model`. Template profiles all use `claude-opus-5`, with `high` effort for orchestration, planning, and review, `medium` for build and design, and `low` for bounded research.
- `pricing_microusd_per_million_tokens` supplies `cost_microusd`; an unpriced model fails closed rather than costing zero. Update `pricing_verified` when you refresh the table.
- `server_side_fallbacks` stays `false` unless a human enables it; a silent model substitution would break the fixed-primary-model rule.
- Only declared kernel tools are sent; any other `tool_use` is refused. Retries are bounded by `max_retries`; a refusal, `max_tokens` stop, or other 4xx error fails the step closed.

## Adapter protocol

Requests contain the exact project/run/contract identity, active agent and model profile, task, step, remaining budgets, capability descriptors, prior trusted tool results, bounded adapter state, and a security boundary declaring project content untrusted.

Responses must contain exactly:

```json
{
	"type": "model_response",
	"protocol_version": 2,
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

The request version follows the reviewed contract schema: schema v1 sends protocol v1, while schema v2 and v3 send protocol v2. This lets a strict old adapter reject unknown request fields safely. A schema-v2 or v3 run may still accept a v1 response only as a controlled compatibility lane, and only with the v1 legacy usage shape. v2 adds the cache-telemetry receipt below; a v2 adapter that receives a v1 request must use a v1 legacy response instead. An unknown version or a v1 response with v2-only fields is refused, so version drift cannot silently reinterpret billing data.

### Usage and cache telemetry

The legacy `usage` shape above remains valid for adapters that cannot truthfully expose cache counters; its cache telemetry is `UNAVAILABLE`. An adapter with provider-supported telemetry may instead return this complete extended shape:

```json
{
	"input_tokens": 1200,
	"cache_read_input_tokens": 800,
	"cache_creation_input_tokens": 100,
	"output_tokens": 300,
	"cost_microusd": 42000
}
```

In the extended shape, `input_tokens` is Harness's canonical total input after adapter normalization, not a copied raw provider field. The all-or-nothing, non-negative cache-read and cache-creation counters are disjoint subsets of that total, so their sum cannot exceed it. For example, an Anthropic-style raw receipt with 8 uncached input, 5,120 cache-creation input, and 0 cache-read input becomes canonical `input_tokens: 5128`. Provider names and billing semantics differ, so an adapter must omit both counters when it cannot map them faithfully—never substitute zero for unknown data or claim a cache hit from session continuity alone.

Each accepted response writes its validated `usage` into a `model_responded` trace receipt. `harness trace usage` labels a complete legacy/unsupported receipt `UNAVAILABLE`; if a response receipt itself is missing or no response exists, the observation is `UNKNOWN`. It calculates cache-read share against canonical `input_tokens` only when every underlying receipt fully reports it. That share is not a cache-hit, pricing, or retention claim.

## Verifier output evidence

`verifier.run` returns a bounded, line-aware preview to the model: matching error-like lines and the final output lines are retained before ordinary noise. The preview is for diagnosis, not an instruction channel. Treat every verifier byte as untrusted data; it has no authority to change tools, scope, approval, or policy.

The complete captured bytes stay local under `.harness/.cache/execution-runs/<run>/outputs/`, in a request-digest-named file. The result records its relative path, byte count, SHA-256 digest, and whether capture was complete; at the smallest declared model-output cap, that metadata remains in the completed-call record while the model gets a compact receipt. A timeout, output limit, or capture failure can produce `complete: false`; absence from the preview is then not evidence that a line never occurred. Evidence is also capped at 16 MiB per run: Harness reduces the final capture to remaining capacity or refuses dispatch before no safe capture remains. Resume validates each evidence file and the aggregate budget, failing closed if either is missing, altered, or over budget.
