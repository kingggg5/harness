# Durable async tool operations

Read this when a task needs long-running tools, user steering during execution, cancellation, resumable background work, or fewer model turns around tool waits. Do not add an async manager to a finite workflow merely because an upstream agent uses one; measure the wait pattern and token cost first.

## What the Unreal Agent source does

The inspected source is the public Unreal Agent repository at commit [`b7c9bf1c5c2fa4127255c07727a7c8413e23944a`](https://github.com/unreallabsai/unreal-agent/tree/b7c9bf1c5c2fa4127255c07727a7c8413e23944a), released under the [MIT License](https://github.com/unreallabsai/unreal-agent/blob/b7c9bf1c5c2fa4127255c07727a7c8413e23944a/LICENSE). Its README and implementation separate five responsibilities:

- The coordinator is the single writer for session decisions. It accepts durable user/control inputs, model responses and operation updates in one event loop.
- A tool translator validates a model call and emits serializable operation descriptions. It must not perform I/O or block the coordinator.
- An operation manager owns execution, cancellation and progress for versioned operations with stable IDs, status, checkpoint state, idempotency data and bounded output.
- The session store appends inputs, turns, responses and tool-call status. It saves a tool-call status with its initial operations together, and returns unfinished operations for recovery.
- The context builder replaces an in-flight tool result with a small running status. When its operation completes, the model receives the final result. A short grace period lets quick operations finish before requesting another model turn.

See the concrete contracts in `harness/coordinator/loop.go`, `harness/operation/operation.go`, `harness/operation/local_manager.go`, `harness/sessionstore/sessionstore.go` and `harness/contextbuilder/builder.go` in that revision.

One README/interface claim is ahead of its default builder implementation: `contextbuilder.Result` defines a report for omitted/truncated/compacted items, but `builder.Build()` currently returns the request with an empty report. Treat omission reporting as a design hook that still needs implementation and validation, not a measured capability of this checkout.

The useful cost mechanism is not concurrency by itself. The model can launch independent useful work once, receive a compact running receipt, and continue while operations run. Completion is later delivered with the original call ID. Heartbeats should be sparse and useful: every heartbeat sent to the model is another request with input and output tokens.

## What the benchmark supports

The [Unreal Labs article](https://unreallabs.ai/blog/unreal-agent/) reports up to 40% lower cost on its workloads and attributes the savings to lower prompt/tool-output overhead and more useful work per model turn. Its Terminal-Bench table reports equal 57.9% task rate and 28 versus 37 turns; the SWE-Atlas table reports 65.8% versus 63.3%, 898k versus 1.69M input tokens, and 16 versus 22 turns. These are vendor-reported comparisons, not Harness results.

The checked-in Harbor adapter at that revision maps token totals into trajectories and explicitly leaves `cost_usd` unknown. The article's dollar totals cannot be reconstructed from that adapter alone; do not repeat them as independently verified measurements. The benchmark runner also requires a configured model provider and Docker or Modal, so the Harness integration does not run those paid trials by default.

## Provider cache affinity

The Unreal Agent coordinator passes a stable session ID as a cache key. Its Responses API adapter hashes the ID, then places it according to the provider adapter: for example, a provider-specific prompt-cache field or session-affinity header. Its OpenRouter adapter also enables an explicit prompt-cache extension. This is provider routing/caching behavior, not one portable API contract.

Harness's Anthropic adapter currently marks its stable system prompt as an ephemeral cache block and records provider-reported cache-read and cache-write tokens in the run trace. The provider-neutral kernel can preserve reported counters, but a cache-key placement capability is not shared across the available adapter interface. Schema-v3 also rebuilds query context, so old context should not be forced into a turn just to keep a cache prefix warm.

If adding cache affinity to a provider adapter:

- Use one stable, opaque key per session and map it through a provider-specific adapter. Hashing makes a key deterministic; it does not make a sensitive identifier secret.
- Keep the reusable prefix byte-stable and put task-varying context after it where the provider's rules allow. Never promise that a key produces a cache hit.
- Verify the current provider/model's cache fields, lifetime, eligibility, pricing and telemetry before relying on them. These vary and can change.
- Record actual input, cache-read, cache-write and output counters per turn. Compare them on a fixed task set and model before claiming savings. The second Jev research pass ranked stable provider cache affinity as the next pattern to document (confidence 0.76; `jev-1.13.0`, 1,233 input and 74 output tokens).

## Bounded tool results

For long output, Unreal's shell operation keeps bounded stdout/stderr head and tail data, full byte sizes and durable capture paths. Its model-facing result carries a truncation marker and points to the full capture, including on failure or cancellation. This is a useful contract for future Harness tools: make the preview small, make truncation explicit, keep full evidence local, and expose a scoped retrieval path. Harness's verifier tool already follows this pattern; workspace reads currently return a bounded prefix, so any head/tail change should be based on code-reading workloads and retain its digest/truncation metadata.

## Turn scheduling details

Unreal's one-second grace window waits briefly for just-launched operations before spending another model request. It separately supports an optional heartbeat while the model is waiting on operations. A heartbeat is still a model turn and costs tokens, so set a long bounded interval or keep it disabled when the user has no need for progress narration. A newly submitted user message can interrupt an in-flight model request; that improves steering, but may waste tokens already processed by the canceled request. Treat those as latency/UX controls, not automatic cost wins.

## Harness fit and limits

Harness already has a durable hash-chained run ledger, a persisted pending-action receipt, scoped tool capabilities, approvals, verifier isolation, output limits, full verifier evidence and recoverable model/tool state. Its finite execution kernel also accepts up to eight tool calls in one response. At this revision, however, `process_pending_tool()` executes them sequentially and waits for each result; the CLI run has no live user-input inbox while it executes. The separate task-graph receipts coordinate node state but do not turn the execution kernel's tools into background operations.

For a real async extension, preserve these invariants:

1. Keep the coordinator as the only writer of canonical run state. Workers return immutable operation updates; they never edit the run ledger.
2. Validate capabilities, paths, model trust and approvals before committing an operation. Bind its ID to the exact call arguments, contract digest and idempotency key.
3. Persist the call status and operation spec before dispatch. On resume, reconcile by operation ID; never guess whether an external effect happened.
4. Version each serializable operation type and checkpoint. Bound concurrency, execution time, queued work and result size; support cooperative cancel and explicit failed/unknown outcomes.
5. Replace the model-facing result with a compact running receipt. Include the operation ID, expected completion signal and a useful independent next action. Deliver the final result under the original tool-call ID.
6. Keep full output in bounded local evidence or artifact files. Send the model a concise summary, error/tail evidence and a stable retrieval path/digest.
7. Measure whether returning to the model while work continues avoids a model wait turn. If there is no independent work, wait in the coordinator without periodic LLM polling.

This requires an explicit schema/protocol change and an input surface for steering. Adding threads around the current sequential `execute_tool()` would bypass its approval, pending-action, evidence-budget and single-writer recovery assumptions. The current schema-v3 Jev context fix is small and isolated; the async manager is a separate architecture project.

## Language choice for this Harness

Keep the current Python runtime and Node launcher. The tracked repository has about 20,052 Python source lines across 33 files, compared with 345 JavaScript and 480 MJS lines; it has no Go, Rust or TypeScript source and no npm runtime dependencies. The Python kernel already owns closed contracts, provider-independent state, Windows/Linux verifier containment, the hash-chained run ledger, approvals, usage and recovery. A full rewrite would recreate those security and compatibility guarantees before it could deliver any token savings.

The upstream Go runtime is a useful example for operation ownership and event-loop boundaries. Go 1.27 is current at this inspection date, and Go's concurrency primitives fit that runtime shape. That does not make Go a model-token optimization by itself. The observed Harness saving came from removing duplicate context bytes, independent of implementation language. A Go binary would also require per-platform builds, signatures, SBOMs, release/update handling and a stable Python-to-Go state protocol. Rust adds a larger language and migration learning cost; TypeScript keeps the existing Node launcher but does not remove the Python policy/runtime boundary unless that is also rewritten.

Jev ranked `keep_python` first (confidence 0.98; `jev-1.13.0`, 1,014 input and 69 output tokens) when given the repository counts, runtime/security requirements and the measured nature of the existing token saving. Its output was advisory; the decision follows from the same evidence. Prototype async operations in the current Python architecture only after representative traces show that sequential tool scheduling causes extra model turns or paid waiting work. Consider a Go component only if a bounded prototype shows a material gain that Python cannot meet and the team accepts the packaging and cross-language support burden. Do not migrate canonical state as part of a prototype.

## Cost and quality measurement

Before and after, run the same task corpus with the same provider, model, reasoning effort, tool permissions, environment and verifiers. Record per-task provider-reported input/output/cache tokens, model requests, turns, tool calls, wall time, and task/policy pass rates. Keep paired task IDs and report means plus variation. Convert tokens to dollars only with the actual provider/model price and date recorded. A lower token total with lower task or policy success is not a cost improvement.

## Jev-guided inclusion

Jev reviewed bounded summaries of the public repository and current Harness architecture. It chose `durable_operation_lifecycle` as the operation guidance to add, with confidence 1.0 (served model `jev-1.13.0`; 1,023 input and 70 output tokens), then ranked stable provider cache affinity as the next pattern to document, with confidence 0.76 (1,233 input and 74 output tokens). Only source summaries were sent to Jev. It rejected wholesale Go SDK copying and unbounded asynchronous execution.
