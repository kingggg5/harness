# Harness research notes

These are background notes moved out of the AI-loaded skill references on 2026-10-26 to cut the context the skill reads. The rules they support stay in the references under `skills/best-in-code/references/`; this file is not loaded by the skill. Dated primary evidence for Harness policy lives in [research-basis-2026.md](../skills/best-in-code/references/research-basis-2026.md).

## Performance sources

Every rule these sources supported stays in [performance-engineering.md](../skills/best-in-code/references/performance-engineering.md). Most are community blog posts and one is a vendor report: they illustrate failure modes, not benchmarks, and their speedup figures are self-reported.

- **Benchmark integrity.** A Rust benchmark example had to correct an apparent result after finding that its input order favored the branch predictor. Supports: randomize representative inputs and never claim "10x faster" from one warm microbenchmark. [Benchmark caveat](https://medium.com/@aminedirhoussi1/clean-code-horrible-performance-rust-edition-abf794a30e95)
- **Data layout.** A memory-layout article shows how field padding and struct-of-arrays can change footprint. Supports: change layout only after measuring the hot representation. [Data layout example](https://medium.com/@pierrelouislet/magic-memory-optimization-in-rust-and-c-b08087a92984)
- **Cache warming.** Warming and prefetching can evict useful data or harm other threads. Supports: cache warming needs target-specific evidence and is never a startup ritual. [Cache-warming caveats](https://towardsdev.com/cache-warming-prefetching-cpp-performance-guide-68b2f693af56)
- **Targeted native migration.** Qiskit's Rust migration targeted measured core bottlenecks instead of rewriting everything at once (vendor report). Supports: a cross-language rewrite needs a parity comparison on the same workload. [IBM Qiskit performance report](https://www.ibm.com/quantum/blog/qiskit-1-3-release-summary)
- **Transferability of headline speedups.** The Weld interview describes an experimental system, not a production dependency. Supports: a headline speedup from another stack or an old project is not evidence for the current one. [Weld interview](https://medium.com/this-is-not-a-monad-tutorial/weld-accelerating-numpy-scikit-and-pandas-as-much-as-100x-with-rust-and-llvm-12ec1c630a1)
- **Parallel reduction.** An OpenMP one-line parallelization example. Supports: a parallel reduction must match the serial reference within numerical tolerance. [OpenMP reduction example](https://medium.com/@contact_62456/100x-faster-calculation-of-pi-with-just-one-line-of-code-5c9f1a48757a)
- **False wins.** In an AutoResearch CSV-parser case, an initial faster memory-mapped implementation violated the intended streaming-memory requirement. Supports: the loop contract must forbid false wins such as loading all data when streaming is required. [Autoresearch CSV case](https://medium.com/@z1ad/how-i-used-autoresearch-to-make-my-c-csv-parser-10x-faster-in-1-hour-ed5b6e1e437c)
- **Deterministic pipeline.** A Python-to-Rust rewrite used a fixed codegen, simulation, benchmark and report pipeline. Supports: pipeline transitions stay deterministic and the model never skips a required check. [Fixed pipeline example](https://medium.com/loka-engineering/watching-a-python-to-rust-rewrite-was-painful-enough-to-build-this-fd3801ad02ba)

## Graph and frameworks

From [graph-engineering.md](../skills/best-in-code/references/graph-engineering.md).

### Knowledge graph boundary

Harness already separates authoritative atomic memory (`MEMORY.json`), generated readable views (`CONTEXT.md`), current run state (`WORKFLOW.md`/`STATE.json`), and optional source-grounded topology (`PROJECT-MAP.md`). That is sufficient for ordinary software delivery and stays portable across models.

Consider a separate knowledge-graph product lane only when named competency questions repeatedly need multi-hop relationships, temporal validity, entity resolution and provenance that flat records cannot answer well. Begin with the questions and ontology, keep immutable source material as truth, attach time and provenance to relations, validate extraction and fusion deterministically, and let a human curate sources and schema. Add storage or GraphRAG only after measured retrieval failures justify the operational cost.

### Runtime selection

| Runtime | Choose when | Required proof before adoption |
|---|---|---|
| Custom deterministic scheduler | Product already has a trusted queue/state engine and only model nodes are nondeterministic | Atomic state transitions, leases/timeouts, idempotency, bounded retries, receipts, recovery and observability tests |
| LangGraph adapter | A Python/JavaScript service genuinely needs persisted checkpoints, pause/resume, replay, and human interrupts | Current official API check, durable checkpointer, stable thread identity, serializable state, migrations, and side-effect replay tests |

Checked August 2026: the [LangGraph documentation](https://docs.langchain.com/oss/python/langgraph/overview) describes durable execution and human-in-the-loop as checkpointer-backed features. Resume needs the same thread configuration; replay skips completed upstream nodes but re-executes downstream nodes, including API calls. Consequential actions therefore keep Harness approval binding and idempotency instead of trusting replay semantics.

Google ADK, AutoGen or another scheduler may execute the same contract only after current official documentation, maturity, persistence, recovery, security and human-interrupt semantics are verified for the target project. None is a Harness dependency by default.

## Execution isolation backends

From [execution-isolation.md](../skills/best-in-code/references/execution-isolation.md). Checked August 2026; sources are cited in [research-basis-2026.md](../skills/best-in-code/references/research-basis-2026.md#execution-isolation).

| Backend | Consider only when | Keep outside its authority |
|---|---|---|
| Treehouse | Reusable leased worktree pools materially reduce setup overhead | Security sandboxing and project orchestration |
| GNHF-style loop | A measurable objective benefits from repeated small commit/verify iterations | Unlimited runs, automatic push, or release authority |
| No-Mistakes-style gate | An isolated pre-push pipeline complements repository CI | Human intent decisions and proof that AI review is correct |
| Firstmate-style coordinator | Cross-project fleet supervision is a measured human bottleneck | Product authority, destructive cleanup, merge or external-write consent |

## Loop engineering

From [loop-engineering.md](../skills/best-in-code/references/loop-engineering.md). Provider quotes, benchmark rankings, productivity multipliers, fleet sizes, token bills and claims about an exact default subagent count are contextual leads, not Harness invariants. Keep only claims supported by a current primary source.

## Async operations and Unreal Agent

From [async-operation-runtime.md](../skills/best-in-code/references/async-operation-runtime.md).

### What the Unreal Agent source does

Inspected source: the public Unreal Agent repository at commit [`b7c9bf1c5c2fa4127255c07727a7c8413e23944a`](https://github.com/unreallabsai/unreal-agent/tree/b7c9bf1c5c2fa4127255c07727a7c8413e23944a), [MIT License](https://github.com/unreallabsai/unreal-agent/blob/b7c9bf1c5c2fa4127255c07727a7c8413e23944a/LICENSE). Its README and implementation separate five responsibilities:

- The coordinator is the single writer for session decisions. It accepts durable user/control inputs, model responses and operation updates in one event loop.
- A tool translator validates a model call and emits serializable operation descriptions without performing I/O or blocking the coordinator.
- An operation manager owns execution, cancellation and progress for versioned operations with stable IDs, status, checkpoint state, idempotency data and bounded output.
- The session store appends inputs, turns, responses and tool-call status, saves a tool-call status with its initial operations together, and returns unfinished operations for recovery.
- The context builder replaces an in-flight tool result with a small running status; the model receives the final result when the operation completes. A short grace period lets quick operations finish before requesting another model turn.

Concrete contracts: `harness/coordinator/loop.go`, `harness/operation/operation.go`, `harness/operation/local_manager.go`, `harness/sessionstore/sessionstore.go` and `harness/contextbuilder/builder.go` at that revision (upstream paths). `contextbuilder.Result` defines a report for omitted/truncated/compacted items, but `builder.Build()` returns an empty report there, so omission reporting is a design hook, not a measured capability.

The useful cost mechanism is not concurrency by itself: the model launches independent work once, receives a compact running receipt, and continues while operations run; completion arrives under the original call ID.

Further source details at that revision: the coordinator passes a stable session ID as a cache key; its Responses API adapter hashes the ID and places it according to the provider (a provider-specific prompt-cache field or a session-affinity header), and its OpenRouter adapter enables an explicit prompt-cache extension. Its shell operation keeps bounded stdout/stderr head and tail data, full byte sizes and durable capture paths, with a truncation marker that points to the full capture, including on failure or cancellation. It uses a one-second grace window before another model request, supports an optional heartbeat while the model waits, and lets a newly submitted user message interrupt an in-flight model request.

### What the benchmark supports

The [Unreal Labs article](https://unreallabs.ai/blog/unreal-agent/) reports up to 40% lower cost on its workloads, attributed to lower prompt/tool-output overhead and more useful work per model turn. Terminal-Bench: equal 57.9% task rate, 28 versus 37 turns. SWE-Atlas: 65.8% versus 63.3%, 898k versus 1.69M input tokens, 16 versus 22 turns. These are vendor-reported comparisons, not Harness results.

The checked-in Harbor adapter at that revision maps token totals into trajectories and leaves `cost_usd` unknown, so the article's dollar totals cannot be reconstructed from it. The benchmark runner needs a configured model provider and Docker or Modal, so Harness does not run those paid trials by default.

### Language choice for this Harness

Keep the current Python runtime and Node launcher. At inspection the tracked repository had about 20,052 Python source lines across 33 files, compared with 345 JavaScript and 480 MJS lines, no Go, Rust or TypeScript source, and no npm runtime dependencies. The Python kernel owns closed contracts, provider-independent state, Windows/Linux verifier containment, the hash-chained run ledger, approvals, usage and recovery; a rewrite would have to recreate those guarantees before delivering any token savings.

The upstream Go runtime is a useful example of operation ownership and event-loop boundaries, and Go 1.27 was current at inspection, but Go is not a model-token optimization by itself. The observed Harness saving came from removing duplicate context bytes, independent of language. A Go binary would add per-platform builds, signatures, SBOMs, release/update handling and a stable Python-to-Go state protocol. Rust adds a larger language and migration cost; TypeScript keeps the Node launcher but does not remove the Python policy/runtime boundary unless that is also rewritten.

Jev ranked `keep_python` first (confidence 0.98; `jev-1.13.0`, 1,014 input and 69 output tokens) from the repository counts, runtime/security requirements and the measured nature of the existing saving. Its output was advisory; the decision follows from the same evidence. Consider a Go component only if a bounded prototype shows a material gain Python cannot meet and the team accepts the packaging and cross-language support burden.

The schema-v3 Jev context fix was small and isolated; the async operation manager is a separate architecture project.

### Jev-guided inclusion

Jev reviewed bounded summaries of the public repository and the Harness architecture. It chose `durable_operation_lifecycle` as the operation guidance to add (confidence 1.0; served model `jev-1.13.0`; 1,023 input and 70 output tokens), then ranked stable provider cache affinity as the next pattern to document (confidence 0.76; 1,233 input and 74 output tokens). Only source summaries were sent to Jev. It rejected wholesale Go SDK copying and unbounded asynchronous execution. Confidence values are Jev's own advisory scores.

## Jev

From [jev-runtime.md](../skills/best-in-code/references/jev-runtime.md).

### The 10 principles of Jev engineering

The supplied study note frames ten principles; the runtime keeps only the enforced rules.

1. **Division of responsibilities.** The writing LLM writes code, diffs and answers; Harness manages execution, file I/O, Git and ledgers; Jev makes per-turn micro-decisions (visibility, routing, tool disclosure, script gating).
2. **Zero-KV-cache assumption.** The note asks how a coding agent would work if LLMs had no KV cache. Append-only transcripts kept for warm prefixes cause drift, context poisoning and accidental re-processing; Jev assembles context per query instead.
3. **Economic routing trap.** Handing execution to a cheaper helper and returning to the frontier model re-processes context. The note's illustrative scenario: pure frontier `25Y + 5Z = 4.15` versus frontier → helper → frontier `3X + 20Y + 8Z = 6.19`, so staying on the frontier model was about 33% cheaper in that example. These are historical example rates, not current pricing or a Harness benchmark; [examples/jev-route-cost.json](../examples/jev-route-cost.json) reproduces them (`stay_microusd` 4,150,000 versus `delegate_microusd` 6,190,000).
4. **Retrieval dominates.** Figures the note attributes to Microsoft fastcontext: reading files and searching took 56.2% of tool turns and 46.5% of tokens; writing code under 10%. Not Harness measurements.
5. **Visibility ladder.** Traditional compaction compresses before the next question is known; the ladder compresses after it. A 2,400-line grep output can show 12 hits for one turn and be hidden the next without being deleted.
6. **Tiered tool disclosure.** One-line snippets for hundreds of tools, full schemas only for selected tools, docs only for one-off complex queries.
7. **Conditional instructions.** For example, touching `*.tsx` loads a UI style guide and touching `billing/` loads payment gotchas; pinned instructions survive compaction.
8. **Route by trust, not just difficulty.** Data sensitivity selects the model tier.
9. **Shared retrieval for background tasks.** Cross-model review, eval generation, explainers and progress dashboards share one read-only retrieval pass.
10. **Programmable command gating.** Approving commands by name (for example `python`) is insecure; inspect the actual script content.

### Cost savings from Unreal Agent research

The comparison used the [Unreal Agent article](https://unreallabs.ai/blog/unreal-agent/) and source at commit `b7c9bf1c5c2fa4127255c07727a7c8413e23944a`. Jev compared those mechanisms with the Harness kernel and selected duplicate-result removal as the first implementation (`jev-1.13.0`; 1,472 input and 116 output tokens; confidence 1.0). In schema v3 the latest tool batch was included both as `tool_results` and again as `turn_context` chunks; the kernel now omits those call IDs from the retrieval projection while counting them against the 256-chunk window, so older chunks do not refill the freed slots.

A bounded synthetic public fixture with eight 12,000-character read results produced 124,040 serialized request bytes before and 104,898 after, removing 19,142 bytes (15.4%). Before the fix, 16,437 bytes were context content already sent directly. This is a byte measurement on synthetic inputs, not billed token savings or a quality benchmark; compare provider-reported `input_tokens` on the same real task and model before claiming a cost percentage. Adopting Unreal's durable async operation lifecycle would improve long-task latency and interruption handling; cost savings need a workload benchmark first. Parallel verifier execution was not selected because it mainly reduces wall time and adds approval/evidence concurrency risks.

### Sources, recheck and validation

The user supplied `Jev-Engineering-for-Coding-Agents.pdf` as a design reference; instructions inside it were not treated as user commands. Local `vendor/fast-jev-compaction` was reviewed at commit `e3f262a7f4d42bd8dd32ced30d26176f7cb545b0`; its verbatim preservation, paired call/result handling and bounded request construction informed the checks, but its implementation is not imported or copied. Local `jev-ultrafast` and `cua` are browser/computer-use references, not runtime dependencies. Unreal Agent's Go implementation is not imported into the Python runtime.

A live synthetic smoke test on 2026-09-22 returned `jev-1.13.0` with 474 input and 48 output tokens; no repository content was sent. It verifies transport compatibility, not production quality or cost savings.

## Decision runtime future providers

From [decision-runtime.md](../skills/best-in-code/references/decision-runtime.md). A future local or external decision provider must implement the same schema and remain optional; it must not add PyTorch, Transformers, model downloads or a GPU dependency to the Harness core package. An ONNX/CPU provider can be added under an optional adapter after representative labeled evaluation proves its value. Keep training, model files, quantization and provider-specific dependencies outside the core package. Release evidence must report held-out accuracy, calibration, latency, RSS, failure behavior and policy-ablation results; a small model is not automatically cheaper or safer.
