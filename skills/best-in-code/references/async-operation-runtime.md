# Durable async tool operations

Read this when a task needs long-running tools, user steering during execution, cancellation, resumable background work, or fewer model turns around tool waits. Do not add an async manager to a finite workflow merely because an upstream agent uses one; measure the wait pattern and token cost first.

## Provider cache affinity

Harness's Anthropic adapter marks its stable system prompt as an ephemeral cache block and records provider-reported cache-read and cache-write tokens in the run trace. The provider-neutral kernel preserves reported counters, but cache-key placement is not part of the shared adapter interface. Schema v3 rebuilds query context, so do not force old context into a turn just to keep a cache prefix warm.

If adding cache affinity to a provider adapter:

- Use one stable, opaque key per session and map it through a provider-specific adapter, such as a prompt-cache field or session-affinity header. Hashing makes a key deterministic; it does not make a sensitive identifier secret.
- Keep the reusable prefix byte-stable and put task-varying context after it where the provider's rules allow. Never promise that a key produces a cache hit.
- Verify the current provider/model's cache fields, lifetime, eligibility, pricing and telemetry before relying on them. These vary and can change.
- Record actual input, cache-read, cache-write and output counters per turn. Compare them on a fixed task set and model before claiming savings.

## Bounded tool results

For long output, keep the model-facing preview small (bounded head and tail), mark truncation explicitly, keep the full capture and byte sizes in local evidence, including on failure or cancellation, and expose a scoped retrieval path. Harness's verifier tool already follows this pattern; workspace reads return a bounded prefix, so any head/tail change should be based on code-reading workloads and retain its digest/truncation metadata.

## Turn scheduling

The cost gain comes from launching independent work once, returning a compact running receipt, and continuing useful work while operations run, not from concurrency by itself. A short grace window can let just-launched operations finish before another model request. An optional heartbeat while the model waits is still a model turn that costs tokens: set a long bounded interval or keep it disabled when the user has no need for progress narration. Letting a new user message interrupt an in-flight model request improves steering but may waste tokens the canceled request already processed. Treat these as latency/UX controls, not automatic cost wins.

## Harness fit and limits

The current kernel in [execution-runtime.md](execution-runtime.md) already has the durable ledger, pending-action receipts, approvals, verifier isolation and evidence limits. It accepts up to eight tool calls per response but `process_pending_tool()` executes them sequentially, the CLI run has no live user-input inbox, and task-graph receipts do not turn kernel tools into background operations.

For a real async extension, preserve these invariants:

1. Keep the coordinator as the only writer of canonical run state. Workers return immutable operation updates; they never edit the run ledger.
2. Validate capabilities, paths, model trust and approvals before committing an operation. Bind its ID to the exact call arguments, contract digest and idempotency key.
3. Persist the call status and operation spec before dispatch. On resume, reconcile by operation ID; never guess whether an external effect happened.
4. Version each serializable operation type and checkpoint. Bound concurrency, execution time, queued work and result size; support cooperative cancel and explicit failed/unknown outcomes.
5. Replace the model-facing result with a compact running receipt. Include the operation ID, expected completion signal and a useful independent next action. Deliver the final result under the original tool-call ID.
6. Keep full output in bounded local evidence or artifact files. Send the model a concise summary, error/tail evidence and a stable retrieval path/digest.
7. Measure whether returning to the model while work continues avoids a model wait turn. If there is no independent work, wait in the coordinator without periodic LLM polling.

This requires an explicit schema/protocol change and an input surface for steering. Adding threads around the current sequential `execute_tool()` would bypass its approval, pending-action, evidence-budget and single-writer recovery assumptions. Prototype async operations in the current Python architecture only after representative traces show that sequential tool scheduling causes extra model turns or paid waiting work, and do not migrate canonical state as part of a prototype.

## Cost and quality measurement

Before and after, run the same task corpus with the same provider, model, reasoning effort, tool permissions, environment and verifiers. Record per-task provider-reported input/output/cache tokens, model requests, turns, tool calls, wall time, and task/policy pass rates. Keep paired task IDs and report means plus variation. Convert tokens to dollars only with the actual provider/model price and date recorded. A lower token total with lower task or policy success is not a cost improvement.
