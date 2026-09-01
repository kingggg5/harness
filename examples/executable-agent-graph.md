# Executable multi-agent graph

Use this example after a Harness task has an active Project ID and Run ID. It demonstrates the provider-neutral execution protocol without granting a model raw shell or filesystem access.

## 1. Copy the pinned templates

```bash
cp .harness/runtime/assets/templates/RUN-CONTRACT.json .harness/RUN-CONTRACT.json
cp .harness/runtime/assets/templates/ADAPTER-ARGV.json .harness/ADAPTER-ARGV.json
```

PowerShell equivalent:

```powershell
Copy-Item .harness/runtime/assets/templates/RUN-CONTRACT.json .harness/RUN-CONTRACT.json
Copy-Item .harness/runtime/assets/templates/ADAPTER-ARGV.json .harness/ADAPTER-ARGV.json
```

Set the contract's `project_id` and `run_id` from `.harness/IDENTITY.json` and `.harness/STATE.json`. Replace the example verifier argv and narrow the write scope before using a real adapter.

For a harmless protocol smoke test, keep the bundled deterministic adapter and set:

```json
"task": "Run delegate-demo through the planner role."
```

The Project Manager delegates to Planner, receives the child result, and finishes. No model API or network access is used.

## 2. Validate, run, and inspect

```bash
npx github:kingggg5/harness run-validate --project . --contract .harness/RUN-CONTRACT.json --adapter-argv-file .harness/ADAPTER-ARGV.json --json
npx github:kingggg5/harness run --project . --contract .harness/RUN-CONTRACT.json --adapter-argv-file .harness/ADAPTER-ARGV.json --json
npx github:kingggg5/harness run-status --project . --contract .harness/RUN-CONTRACT.json --json
```

Try a human pause by changing the task to include `approval-demo`. The run returns `WAITING_APPROVAL` with an `APR-...` request:

```bash
npx github:kingggg5/harness run-approve --project . --contract .harness/RUN-CONTRACT.json --request-id APR-... --decision approved --actor your-name --json
npx github:kingggg5/harness run --project . --contract .harness/RUN-CONTRACT.json --adapter-argv-file .harness/ADAPTER-ARGV.json --json
```

The receipt is tied to the exact artifact and action. Editing the receipt, contract, runtime, state, or trace causes validation to fail rather than silently continuing.

## 3. Replace the demo adapter

A real adapter maps portable `model_profile` values to models available in its provider and returns the closed response documented in the [execution runtime guide](../skills/best-in-code/references/execution-runtime.md). Keep it in a reviewed external file or package and point `ADAPTER-ARGV.json` to an exact argv array. Use `@harness-python` as the first item for a Python adapter, or an absolute executable path for another runtime; raw PATH names such as `python` or `node` are intentionally rejected. Do not add shell strings, let repository content choose a model/tool, or pass the whole environment by default.

Suggested portable mapping:

| Profile intent | Example route |
|---|---|
| Orchestration, planning, high-risk review | Sol-class reasoning model |
| Frontend/backend/design implementation | Terra-class balanced model |
| Bounded research, extraction, low-risk analysis | Luna-class fast model |

The mapping is a policy owned by the human/provider adapter. The kernel records the profile requested; the adapter should record the actual model used in its own trusted telemetry.
