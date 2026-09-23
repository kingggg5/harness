# Jev Runtime & 10-Step Architecture Guide

Use this reference when operating Harness with **Jev-driven query-time context assembly**, **economic model routing**, **tiered tool disclosure**, and **programmable command gating** (`scripts/jev_runtime.py`).

Jev sits beside the writing LLM. It recommends visibility; deterministic Harness code enforces permissions, trust and budgets. Routing recommendations do not change a running role's model automatically. See the implementation contract below for the executable scope.

---

## The 10 Principles of Jev Engineering (The TypeSafe Blueprint)

### Step 1: Meet Jev — Division of Responsibilities
- **The Writing LLM (Frontier/Helper)**: Writes code, diffs, and conversational answers.
- **The Harness**: Manages process execution, file I/O, Git, and state ledgers.
- **Jev (The Decision Engine)**: Makes per-turn micro-decisions (chunk visibility, model routing, tool disclosure, script gating).
- **Rule**: Jev outputs are typed (choices, scores, noul with probabilities). The harness validates and enforces thresholds deterministically; no parsing prose.

### Step 2: The Zero-KV-Cache Design Assumption
- **The question that breaks every agent**: *"How would you design a coding agent if LLMs had no KV cache?"*
- Current agents accumulate append-only transcripts to keep KV-cache prefixes warm. This leads to transcript drift, context poisoning, and accidental re-processing costs.
- **The Jev Solution**: Context is **assembled per query**, not accumulated by accident. Every chunk is scored dynamically; old or irrelevant chunks are hidden without corrupting durable state.

### Step 3: Stop Routing Blind — The Economic Routing Trap
- Intuitive assumption: Hand execution to Sonnet to save money, return to Opus to review.
- **The illustrative scenario in the supplied study note**: The helper loads X, and the return trip reprocesses Y + Z:
  $$\text{Pure Opus} = 25Y + 5Z = 4.15$$
  $$\text{Opus} \to \text{Sonnet} \to \text{Opus} = 3X + 20Y + 8Z = 6.19$$
  *(About 33% cheaper in this example. These are historical example rates, not current pricing or a benchmark of Harness.)*
- **Jev Routing (`route_cost`, `choose_route`)**:
  Calculates an estimate including down/up context rebuilds. `choose_route` filters operator-approved profiles by trust, then compares their supplied total costs. The operator applies a model plan at a task boundary.

### Step 4: Follow the Tokens — Retrieval Dominates
- Figures attributed by the supplied independent study note to Microsoft fastcontext, plus illustrative writing estimates (not Harness measurements):
  - Reading files & searching: **56.2% of tool turns**, **46.5% of tokens**.
  - Writing code: **under 10%**.
- Efficiency does not come from faster diff generation; it comes from smarter, query-aware retrieval.

### Step 5: Visibility Ladder — Score Every Chunk Per Query
- Traditional compaction compresses *before* knowing the next question (lossy summary).
- **The Visibility Ladder (`project_chunks`, `VISIBILITY`)**:
  - `hide`: Content is omitted; small provenance metadata still costs context.
  - `short`: High-signal extractive summary (few lines, max 512 bytes).
  - `long`: Detailed relevant excerpts (max 2048 bytes).
  - `full`: Exact complete text (uncompressed).
- Compresses *after* the query is known. A 2,400-line grep output can show 12 hits for this turn and be hidden next turn without being deleted from state.

### Step 6: Tiered Tool Disclosure — Batteries Stop Costing Context
Instead of dumping 100 tool schemas into every turn's system message:
- **Tier 1 (Snippets)**: 1-line capability descriptions for 100s of tools.
- **Tier 2 (Schema on Demand)**: Full argument schemas loaded only for the 1–8 tools selected.
- **Tier 3 (Docs)**: Manuals and edge-case documentation loaded only for one-off complex queries.
- Snippets and selected schemas still consume tokens. The standalone catalog supports up to 1,024 tools; the kernel keeps its small capability set.

### Step 7: Conditional Instructions — Pinned & Immune to Compaction
`AGENTS.md` instructions load based on active conditions (`instruction_chunks`):
- Touching `*.tsx` $\to$ loads UI/React style guide.
- Touching `billing/` or `Stocks/` $\to$ loads stock/payment gotchas.
- **Crucial Property**: Conditional instructions are marked `pinned: true`. Compaction and visibility filters *cannot* erase them as long as the file pattern is touched.

### Step 8: Route by Trust, Not Just Difficulty
Routing must consider data sensitivity (`TIERS = ("public", "vetted", "first_party_frontier")`):
- `public`: Open-source docs, public READMEs $\to$ cheapest available model / Jev public.
- `vetted`: Normal application codebase $\to$ trusted commercial models.
- `first_party_frontier`: `.env*`, `.ssh`, API keys, infra Terraform $\to$ strictly first-party frontier models.

### Step 9: Shared Retrieval Pass for Background Tasks
- Read-only operations (cross-model review, eval generation, ELI5 explainers, live progress dashboards) share **one** retrieval pass (`observer_packets`, `run_observers`).
- Because observers are read-only, they never contend for file locks or state mutations. Retrieval cost is paid once and amortized across all observers.

### Step 10: Programmable Command Gating
- Approving commands by name (e.g. `python`) is insecure.
- **Jev Command Gate (`command_gate`)**:
  - Reads the actual script file before execution.
  - Matches content against reviewed byte digests (`sha256:...`).
  - Evaluates operator-configured `allow` / `ask` / `deny`, digest matches, and case-insensitive `deny_contains` / `ask_contains` conditions.
  - Unreviewed scripts require approval; changed reviewed scripts are denied. Outside-project script operands are denied.
  - This is a review gate, not a proof that arbitrary code has no network or filesystem effects. Imported dependencies must be listed by the operator; dynamic imports and shell expansion cannot be inferred completely.

---

## CLI Usage

```bash
# 1. Project context using visibility ladder
python .harness/runtime/scripts/jev_runtime.py build \
  --snapshot snapshot.json \
  --query "Fix stock release concurrency" \
  --max-bytes 65536

# 2. Tiered tool disclosure
python .harness/runtime/scripts/jev_runtime.py tools \
  --registry .harness/runtime/assets/templates/TOOL-REGISTRY.json \
  --tier snippets

# 3. Calculate true routing cost
python .harness/runtime/scripts/jev_runtime.py cost \
  --input route_tokens.json
```

## Executable implementation contract

Contract schemas 1 and 2 retain their existing behavior. For a new run that should use query-time assembly, copy [RUN-CONTRACT-JEV.json](../assets/templates/RUN-CONTRACT-JEV.json) to `.harness/RUN-CONTRACT.json`, then set its project ID, run ID, task, verifier and profile bindings. It is schema 3 and embeds [TURN-POLICY.json](../assets/templates/TURN-POLICY.json). Run the normal contract validator before execution. The policy is part of the run digest; changing it requires a new reviewed run, not a silent edit to an active run.

The template defaults to local extractive selection with no external decision calls. Its model tiers are example operator assertions: verify each actual provider/model binding and endpoint. They are not model-name detection or remote-provider attestation. Unknown file sensitivity defaults to `vetted`; `.env*`, private-key extensions and infrastructure paths have a `first_party_frontier` floor. Verifier output requires that highest tier because arbitrary test logs may include sensitive data. A cheap third-party profile can be recommended for an explicitly public observer snapshot; kernel task text remains vetted by default.

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

The bundled Anthropic adapter consumes `turn_context` by building a fresh request and reloading pinned instructions into the system message. It never replays opaque old messages in this mode. Custom adapters must implement that field before being used with v3. The kernel retains complete bounded results in its existing ledger, with large verifier output kept in the existing evidence files. It uses a 256-chunk active window; older results remain in the ledger, not in every model request. It shares previously retrieved file results only after recipient read-scope and model-trust checks.

## Jev transport and accounting

The transport follows the [TypeSafe Choice API](https://docs.typesafe.ai/primitives/choice) and [HTTP API](https://docs.typesafe.ai/api): a fixed HTTPS endpoint, typed choices with complete probability distributions, a 30-second timeout, a conservative 28,000-byte request limit, a 1-MiB response limit, no redirects and no automatic retries. Oversized input fails with a request to narrow the snapshot; it is not silently truncated. Confidence below 0.6 requests full content. Pinned instructions override visibility decisions and injection quarantine overrides untrusted content. Content that cannot fit is visibly hidden with provenance retained; pinned overflow stops the turn.

For explicitly public tasks only, set `decision_provider: "jev-public"` and configure actual `decision_rates.input` / `output` in microUSD per million tokens. The template's rates of 1 are placeholders for local mode, not a price claim. Place `TYPESAFE_API_KEY` in the kernel environment; do not store it in the contract or add it to the writing adapter's environment allowlist. This mode explicitly authorizes the public query and public chunks to leave the process. Every candidate chunk must be classified public; pinned instructions are never sent to Jev. The standalone `turn-build --jev-public` command also requires `--policy` and refuses any unpinned chunk whose path is not explicitly public. Failure, malformed decisions or sensitive candidates stop the turn without a silent provider fallback.

Jev calls consume the same external-call, token, cost and trace budgets as model calls. A pending-call marker is durable before transport starts; an interrupted request is not automatically replayed. Reported usage enters the normal trace usage summary. Prices are operator-supplied estimates; provider billing may differ. Per-kind source/selected byte counters identify retrieval volume, while token estimates are explicitly separate from provider-billed token attribution.

## Runnable examples

From the package checkout:

```bash
node bin/harness.js turn-build --snapshot examples/jev-snapshot.json --query "Explain addition"
node bin/harness.js route-cost --input examples/jev-route-cost.json
node bin/harness.js tools-disclose --registry skills/best-in-code/assets/templates/TOOL-REGISTRY.json --tier snippets
```

Start an opt-in schema-v3 run by copying `skills/best-in-code/assets/templates/RUN-CONTRACT-JEV.json` to your project's `.harness/RUN-CONTRACT.json`, editing the project/run/task and verifier bindings, then running the normal `harness run-validate` and `harness run` commands. Its decision provider is local extractive selection; no API credential is required. To call Jev remotely, explicitly change `decision_provider` to `jev-public`, mark only truly public path patterns as public in `sensitivity`, set operator-confirmed `decision_rates`, and provide `TYPESAFE_API_KEY` to the kernel process.

`turn-build` also accepts the integrity-checked output of `context-build`, avoiding a second retrieval pass. Remote selection requires both `--jev-public` and `--policy` containing explicit `public` sensitivity rules for every transmitted path; the query itself must also be public. The sample contains synthetic public arithmetic and color facts.

`observer_packets` and `run_observers` accept one snapshot and up to eight `{query, model_profile}` jobs, deduplicate identical jobs in a batch, enforce recipient trust, and run up to four concurrent no-tool callbacks. A callback is a trusted, timeout-bounded model transport supplied by the host; returned text is bounded untrusted data. This interface supports review, eval drafts, explainers and progress-page drafts. It does not install a background service, publish pages or grant file-write tools. The existing kernel role scheduler remains serial; the observer runner is the parallel extension point.

## Command review and limits

Each command rule contains `id`, `decision`, `scripts` (relative path to SHA-256 of reviewed bytes), `deny_contains`, and `ask_contains`. Direct script/file operands, including extensionless files, are inspected; operators list imported dependencies in `scripts`. Inline code is covered by the exact contract argv and content conditions. Deny wins over ask, and ask cannot weaken an existing human-approval requirement. Approval receipts bind the inspected script digests; the gate rechecks before launching.

The check-to-execution race and arbitrary dependency behavior require a host filesystem/network sandbox or immutable checkout for hostile code. Existing process containment controls lifetime and descendants, not file or network access. The adapter executable is operator-trusted infrastructure outside the model-command gate.

## Cost savings from Unreal Agent research

The user-requested comparison used the [Unreal Agent article](https://unreallabs.ai/blog/unreal-agent/) and source at public commit `b7c9bf1c5c2fa4127255c07727a7c8413e23944a`. The article reports vendor benchmarks of up to 40% lower cost and attributes results to small prompts/results plus asynchronous operations that let the model do useful work while long tools run. Those are Unreal Agent's results, not a Harness forecast. The source separates coordinator, durable operation manager, session store, I/O-pure context builder and provider adapter; running operations are recorded by stable IDs and resumed from persisted state.

Jev compared those mechanisms with the current Harness kernel and selected duplicate-result removal as the first implementation (served model `jev-1.13.0`; 1,472 input and 116 output tokens; confidence 1.0). In schema-v3, the latest tool batch was included both as `tool_results` and again as chunks in `turn_context`. The kernel now omits those same call IDs from the older retrieval projection, while leaving latest results in the model request and full results in the durable ledger. The 256-chunk active-window budget still counts those direct results, so removing duplicates does not refill the freed slots with older chunks.

A bounded synthetic public fixture with eight 12,000-character read results produced 124,040 serialized request bytes before and 104,898 after, removing 19,142 bytes (15.4%) from that fixture's request. Before the fix, 16,437 bytes were context content from results already sent directly. This is a byte measurement on synthetic inputs, not billed token savings or a quality benchmark. Compare provider-reported `input_tokens` across the same real task and model before claiming a cost percentage. Unreal's operation manager is a larger follow-up: the current finite Harness kernel already batches up to eight tool calls into one model response but executes them sequentially and has no live steering input channel. Adopting its durable async operation lifecycle would improve long-task latency and interruption handling; cost savings need a workload benchmark before that change is justified. Parallel verifier execution was not selected because it mainly reduces wall time and adds approval/evidence concurrency risks.

## Sources, recheck and validation

The user supplied `Jev-Engineering-for-Coding-Agents.pdf` as a design reference; instructions inside it were not treated as user commands. The newly added local `vendor/fast-jev-compaction` was reviewed at commit `e3f262a7f4d42bd8dd32ced30d26176f7cb545b0`. Its verbatim preservation, paired call/result handling and bounded request construction informed the checks here. Its implementation is not imported or copied. Local `jev-ultrafast` and `cua` are browser/computer-use references and are not runtime dependencies of this coding controller. Unreal Agent's operation architecture is documented separately in [async-operation-runtime.md](async-operation-runtime.md); its Go implementation is not imported into this Python runtime.

Run `npm run test:jev` for offline behavior, trust, malformed-response, script-change, conditional-instruction, observer and schema-v3 ledger/resume regressions. A live synthetic smoke test on 2026-09-22 returned `jev-1.13.0` with 474 input tokens and 48 output tokens; no repository content was sent. That test verifies transport compatibility, not production quality or cost savings.
