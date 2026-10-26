# Jev Runtime

Use this reference when operating Harness with **Jev-driven query-time context assembly**, **economic model routing**, **tiered tool disclosure**, and **programmable command gating** (`scripts/jev_runtime.py`).

Jev sits beside the writing LLM. It returns typed per-turn decisions (choices, scores and bool questions with probabilities); deterministic Harness code validates thresholds and enforces permissions, trust and budgets without parsing prose. Routing recommendations do not change a running role's model automatically.

## Components

| Component | Command or function | Enforced rule |
|---|---|---|
| Query-time context | `turn-build`, `project_chunks` | Context is assembled per query, not accumulated; hidden chunks stay in durable state. |
| Visibility ladder | `VISIBILITY` | `hide` keeps only provenance metadata (which still costs context), `short` ≤ 512 bytes, `long` ≤ 2,048 bytes, `full` exact text. |
| Economic routing | `route-cost`, `route_cost`, `choose_route` | Estimates include the down and return context rebuild. `choose_route` filters operator-approved profiles by trust, then compares their supplied total costs; the operator applies a model plan at a task boundary. |
| Tiered tool disclosure | `tools-disclose`, `disclose_tools`, `tools.describe` | Snippets for up to 1,024 tools; schemas or docs only for 1–8 named tools. Snippets and schemas still consume tokens; the kernel keeps its small capability set. |
| Conditional instructions | `instruction_chunks` | Matching instructions are pinned; visibility filters and compaction cannot remove them while their pattern is touched. |
| Trust routing | `TIERS`: `public`, `vetted`, `first_party_frontier` | Public docs may use the cheapest model or Jev public; the normal codebase needs trusted commercial models; `.env*`, `.ssh`, keys and infrastructure need first-party frontier models. |
| Shared retrieval | `observer_packets`, `run_observers` | Read-only observers share one retrieval pass and never contend for state writes. |
| Command gate | `command_gate` | Reads the script before execution and matches reviewed SHA-256 digests; see [Command review and limits](#command-review-and-limits). |

## Executable implementation contract

Contract schemas 1 and 2 retain their existing behavior. For a new run that should use query-time assembly, copy [RUN-CONTRACT-JEV.json](../assets/templates/RUN-CONTRACT-JEV.json) (`.harness/runtime/assets/templates/RUN-CONTRACT-JEV.json` in a project) to `.harness/RUN-CONTRACT.json`, set its project ID, run ID, task, verifier and profile bindings, then run the normal `harness run-validate` and `harness run` commands. It is schema 3 and embeds [TURN-POLICY.json](../assets/templates/TURN-POLICY.json). The policy is part of the run digest; changing it requires a new reviewed run, not a silent edit to an active run.

The template defaults to local extractive selection with no external decision calls and no API credential. Its model tiers are example operator assertions: verify each actual provider/model binding and endpoint. They are not model-name detection or remote-provider attestation. Unknown file sensitivity defaults to `vetted`; `.env*`, private-key extensions and infrastructure paths have a `first_party_frontier` floor. Verifier output requires that highest tier because arbitrary test logs may include sensitive data. A cheap third-party profile can be recommended for an explicitly public observer snapshot; kernel task text remains vetted by default.

Add conditional instructions explicitly, for example:

```json
"instructions": [
  {"glob": "*", "path": "AGENTS.md"},
  {"glob": "*.tsx", "path": "style-guide.md"},
  {"glob": "billing/*", "path": "billing/GOTCHAS.md"}
]
```

`*` is unconditional. Other patterns match normalized relative paths touched by this agent. Active instruction files are re-read in full every turn and cannot be modified through the model's workspace-write tool. Missing, linked, oversized or over-budget instructions stop the turn. A direct first write into a new condition returns `INSTRUCTIONS_REQUIRED`; the next turn receives the instructions before retrying. Conditions stay active for the role's touched paths during that run.

For tiered disclosure, add `tools.describe` to the contract's tool registry and the applicable roles with empty read/write/exec scopes, `approval: "never"`, and normal bounded input/output/time limits. Initial requests contain snippets plus the describe/human schemas. Calling `tools.describe` with `{"name":"workspace.read","tier":"schema"}` makes that schema available on the next turn; `tier: "docs"` exposes its contract documentation. The existing authorization checks still govern every invocation. Without this capability, v3 retains the complete small kernel tool list.

The bundled Anthropic adapter consumes `turn_context` by building a fresh request and reloading pinned instructions into the system message. It never replays opaque old messages in this mode. Custom adapters must implement that field before being used with v3. The kernel retains complete bounded results in its existing ledger, with large verifier output kept in the existing evidence files. It uses a 256-chunk active window; older results remain in the ledger, not in every model request. The latest tool batch is sent directly as `tool_results` and omitted from `turn_context`, but still counts against that window. It shares previously retrieved file results only after recipient read-scope and model-trust checks.

## Jev transport and accounting

The transport follows the [TypeSafe Choice API](https://docs.typesafe.ai/primitives/choice) and [HTTP API](https://docs.typesafe.ai/api): a fixed HTTPS endpoint, typed choices with complete probability distributions, a 30-second timeout, a conservative 28,000-byte request limit, a 1-MiB response limit, no redirects and no automatic retries. Oversized input fails with a request to narrow the snapshot; it is not silently truncated. Confidence below 0.6 requests full content. Pinned instructions override visibility decisions and injection quarantine overrides untrusted content. Content that cannot fit is visibly hidden with provenance retained; pinned overflow stops the turn.

For explicitly public tasks only, set `decision_provider: "jev-public"`, mark only truly public path patterns as public in `sensitivity`, and configure operator-confirmed `decision_rates.input` / `output` in microUSD per million tokens. The template's rates of 1 are placeholders for local mode, not a price claim. Place `TYPESAFE_API_KEY` in the kernel environment; do not store it in the contract or add it to the writing adapter's environment allowlist. This mode explicitly authorizes the public query and public chunks to leave the process. Every candidate chunk must be classified public and the query itself must be public; pinned instructions are never sent to Jev. The standalone `turn-build --jev-public` command also requires `--policy` and refuses any unpinned chunk whose path is not explicitly public. Failure, malformed decisions or sensitive candidates stop the turn without a silent provider fallback.

Jev calls consume the same external-call, token, cost and trace budgets as model calls. A pending-call marker is durable before transport starts; an interrupted request is not automatically replayed. Reported usage enters the normal trace usage summary. Prices are operator-supplied estimates; provider billing may differ. Per-kind source/selected byte counters identify retrieval volume, while token estimates are explicitly separate from provider-billed token attribution.

## Runnable examples

From the package checkout (the launcher requires Python 3.12+ and runs scripts with `-B`):

```bash
node bin/harness.js turn-build --snapshot examples/jev-snapshot.json --query "Explain addition" --max-bytes 65536
node bin/harness.js route-cost --input examples/jev-route-cost.json
node bin/harness.js tools-disclose --registry skills/best-in-code/assets/templates/TOOL-REGISTRY.json --tier snippets
node bin/harness.js tools-disclose --registry skills/best-in-code/assets/templates/TOOL-REGISTRY.json --tier schema --name repository.read_file
```

In a project, use `harness turn-build`, `harness route-cost` and `harness tools-disclose`, or call the pinned `python -B .harness/runtime/scripts/jev_runtime.py build|cost|tools` directly. `--tier schema` and `--tier docs` require 1–8 repeated `--name` tool IDs. The sample snapshot contains synthetic public arithmetic and color facts.

`turn-build` also accepts the integrity-checked output of `context-build`, avoiding a second retrieval pass.

`observer_packets` and `run_observers` accept one snapshot and up to eight `{query, model_profile}` jobs, deduplicate identical jobs in a batch, enforce recipient trust, and run up to four concurrent no-tool callbacks. A callback is a trusted, timeout-bounded model transport supplied by the host; returned text is bounded untrusted data. This interface supports review, eval drafts, explainers and progress-page drafts. It does not install a background service, publish pages or grant file-write tools. The existing kernel role scheduler remains serial; the observer runner is the parallel extension point.

## Command review and limits

Each command rule contains `id`, `decision` (`allow`, `ask` or `deny`), `scripts` (relative path to SHA-256 of reviewed bytes), and case-insensitive `deny_contains` and `ask_contains` conditions. Direct script/file operands, including extensionless files, are inspected; operators list imported dependencies in `scripts`. Inline code is covered by the exact contract argv and content conditions. Unreviewed scripts require approval; changed reviewed scripts and outside-project script operands are denied. Deny wins over ask, and ask cannot weaken an existing human-approval requirement. Approval receipts bind the inspected script digests; the gate rechecks before launching.

The gate is a review gate, not proof that arbitrary code has no network or filesystem effects; dynamic imports and shell expansion cannot be inferred completely. The check-to-execution race and arbitrary dependency behavior require a host filesystem/network sandbox or immutable checkout for hostile code. Existing process containment controls lifetime and descendants, not file or network access. The adapter executable is operator-trusted infrastructure outside the model-command gate.

## Validation

Run `npm run test:jev` for offline behavior, trust, malformed-response, script-change, conditional-instruction, observer and schema-v3 ledger/resume regressions.
