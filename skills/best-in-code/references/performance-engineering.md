# Cross-Language Performance Engineering

Read this reference only when the requested outcome names latency, throughput, CPU, memory/RSS, allocation rate, startup time, battery/energy, I/O, scale, or a performance-sensitive rewrite. It applies across languages; language-specific tooling stays in the repository or an approved tool backend.

Performance work changes a measured workload, not a programming style. A result is useful only when the same behavior, input contract, error handling, and resource limits still pass.

## Start with a performance contract

Copy `assets/templates/PERFORMANCE-EVIDENCE.md` into the run evidence directory only when this lane is active. Record:

- the user-visible outcome and excluded behavior;
- workload, dataset/input generator, size/distribution, seed, and data digest;
- baseline revision, command, runtime/compiler/database version, host/CPU/OS, and relevant configuration;
- target metric and threshold: p50/p95/p99, throughput, RSS/heap, allocations, CPU, I/O, or cost;
- correctness corpus and deterministic verifier; and
- budget: iterations, elapsed time, threads/concurrency, memory, permitted files, rollback revision, and stop condition.

An unknown workload, baseline, or correctness check is a discovery problem, not permission to guess an optimization. Use [discovery-loop.md](discovery-loop.md) first.

After the project benchmark emits `PERFORMANCE-RESULT.json` for the baseline and candidate, compare them through the dependency-free gate:

```bash
harness perf-check \
	--baseline .harness/evidence/perf-baseline.json \
	--current .harness/evidence/perf-current.json \
	--budget .harness/PERFORMANCE-BUDGET.json \
	--output .harness/evidence/perf-comparison.json \
	--json
```

Validate a newly emitted result before storing it or comparing it:

```bash
harness perf-validate --result .harness/evidence/perf-current.json --json
```

The comparator never runs a benchmark. It rejects unmatched workload digests, optionally mismatched environments, failed correctness evidence, missing budgeted metrics, absolute budget failure, and baseline regression beyond the configured allowance. Each language/toolchain only needs to emit the same closed result schema.

## Verifier binding

The project host owns benchmark execution. Register one read-only verifier ID such as `performance-budget` whose reviewed command first runs the project benchmark, then calls `harness perf-check` with fixed project-relative evidence paths. Keep the actual executable, arguments, timeout, environment allowlist, output cap, and writable evidence directory in the trusted verifier registry—not in an agent prompt, loop contract, or recalled memory. Pair it with a separate deterministic correctness verifier. The performance comparator is evidence only; a PASS never authorizes merge, deploy, publish, or an architecture rewrite.

## Universal experiment sequence

1. **Baseline.** Run the fixed workload enough times to describe variance. Keep cold-start and warm-start results separate.
2. **Profile.** Identify the dominant cost: algorithmic work, data movement, allocation/GC, lock contention, branch misses, I/O, serialization, query plan, or external dependency.
3. **Hypothesize.** Change one causal factor and predict both the performance result and any correctness/resource risk.
4. **Implement.** Make the smallest reversible slice. Preserve public behavior and record any semantic trade-off explicitly.
5. **Verify.** Run the correctness corpus, negative/boundary cases, resource limits, and the same benchmark environment.
6. **Compare.** Keep only a repeatable improvement that meets the target without a material regression. Otherwise revert the loop-owned slice and record the result.

Do not call a result “10x faster” from one warm microbenchmark. Randomize representative inputs where branch prediction or cache state could bias the result, report sample count and distribution, and distinguish emulator-relative comparisons from timing on real target hardware. A Rust benchmark example in the supplied reading had to correct an apparent result after discovering its input order favored the branch predictor. [Benchmark caveat](https://medium.com/@aminedirhoussi1/clean-code-horrible-performance-rust-edition-abf794a30e95)

## Technique ladder

Use the lowest-risk technique supported by profiler evidence. The table describes hypotheses to test, not defaults to apply.

| Observed cost | Cross-language hypothesis | Guardrail |
|---|---|---|
| Too much work | Improve algorithm, remove repeated work, batch operations, precompute stable values | Preserve numeric precision, invalid-input handling, and memory bound |
| Copies or allocations | Reuse buffers, reserve known capacity, pass views/references, stream instead of materializing | Do not retain borrowed/mutable data past its lifetime or introduce shared mutable state |
| Memory bandwidth/cache misses | Traverse contiguous data, keep hot fields close, reduce pointer chasing, choose SoA only for hot-column scans | Layout changes can affect ABI, serialization, cache invalidation, and readability |
| Dispatch/branch overhead | Replace proven hot dynamic dispatch or unpredictable branches with a bounded representation or lookup | Do not eliminate necessary validation or assume a branchless version is faster without measurement |
| Lock/contention bottleneck | Partition independent work, batch synchronization, use bounded queues/backpressure | Prove ordering, cancellation, idempotency, races, and resource isolation |
| CPU-vectorizable loop | Help the compiler prove aliasing/alignment, then inspect vectorization evidence; use SIMD only after that | Keep portable scalar fallback and test every supported CPU/compiler target |
| I/O, database, network | Reduce round trips, use streaming, batch safely, inspect query plans, cache only with invalidation rules | Do not turn a benchmark cache into stale user-visible data or hide network failures |
| Language/runtime overhead | Move one profiled, stable kernel behind a narrow interface or use the native/vectorized backend already in the stack | A rewrite requires end-to-end evidence, migration/operability plan, and a human Decision Gate |

## Writing style by runtime

### Every language

Keep the product-facing API readable and isolate a proven hot kernel behind a small, testable boundary. Prefer explicit ownership, bounded input/output, stable data contracts, and a reference implementation or property test when an optimized representation is hard to inspect. Do not spread cache tricks, pooling, unsafe code, or target intrinsics through ordinary application code.

### C, C++, Rust, Zig, and other native code

Favor sequential access, bounded buffers, data that matches the loop’s access pattern, and compile-time/runtime checks for overflow, alignment, aliasing, and lifetime rules. Field order, padding, array-of-structs versus struct-of-arrays, preallocation, no-copy views, branch layout, and explicit SIMD may matter when a tight loop processes large volumes. The supplied memory-layout article illustrates how padding and SoA can change footprint; use it only after measuring the hot representation. [Data layout example](https://medium.com/@pierrelouislet/magic-memory-optimization-in-rust-and-c-b08087a92984)

Prefetch, cache warming, non-temporal accesses, huge pages, manual allocator changes, atomics, NUMA layout, and CPU intrinsics are specialist techniques. They require target-specific profiler evidence, bounded cache/working-set assumptions, correctness tests, and a fallback. Cache warming can also evict useful data or harm other threads; it is not a startup ritual. [Cache-warming caveats](https://towardsdev.com/cache-warming-prefetching-cpp-performance-guide-68b2f693af56)

### Python, Ruby, JavaScript/TypeScript, PHP, and other dynamic runtimes

First remove unnecessary Python/JS-level loops, conversions, serialization, allocations, and round trips. Batch work, stream large inputs, use the runtime’s established vectorized/native primitives, and isolate a native extension or service boundary only after profiling proves interpreter overhead dominates an otherwise stable kernel. A broad rewrite to Rust/C++ is not an optimization plan by itself; compare feature parity, latency, memory, packaging, debugging, and maintenance cost against the same workload. Qiskit’s Rust migration is a useful example of targeting measured core bottlenecks rather than rewriting everything at once. [IBM Qiskit performance report](https://www.ibm.com/quantum/blog/qiskit-1-3-release-summary)

### JVM, .NET, Go, and managed runtimes

Profile allocation/GC, escape behavior, object layout, serialization, pooling, lock contention, and scheduling before changing code. Prefer built-in profilers and runtime-supported data structures. Reuse/pool only when allocation pressure is measured and ownership/reset rules are explicit; pools can add contention, retained memory, and lifecycle bugs.

### SQL, dataframes, and distributed/data workloads

Start with query plans, data transfer volume, partition/skew, indexes, vectorized/set-based operations, batching, and materialization boundaries. Fuse adjacent transforms only when the engine/runtime can preserve semantics and diagnostics. Do not infer that an old compiler/runtime project or a headline speedup transfers to a current stack; the Weld article itself describes an experimental system rather than a production dependency. [Weld interview](https://medium.com/this-is-not-a-monad-tutorial/weld-accelerating-numpy-scikit-and-pandas-as-much-as-100x-with-rust-and-llvm-12ec1c630a1)

## Parallelism and cache locality

Parallelize only independent partitions with a bounded worker count, deterministic reduction/merge, controlled memory use, and an explicit contention model. Verify one worker through the maximum approved worker count; more threads can reduce performance through false sharing, cache pressure, synchronization, I/O saturation, or non-deterministic output. A parallel reduction must prove the same result and numerical tolerance as the serial reference. [OpenMP reduction example](https://medium.com/@contact_62456/100x-faster-calculation-of-pi-with-just-one-line-of-code-5c9f1a48757a)

For data-oriented changes, measure the actual traversal. SoA is often useful when a hot loop touches only a few fields across many records; AoS can be clearer and faster when each operation consumes a whole record. Keep both representations out of the general architecture until profiling shows the hot loop and data volume justify the added complexity.

## Bounded optimization loops

Use [loop-engineering.md](loop-engineering.md) only when repeated experiment/verify work is justified. Begin with one owner, `max_runs=1`, one fixed workload, and one rollback revision. Each iteration may make one hypothesis-driven change; keep/revert is based on deterministic correctness and comparable performance evidence.

The loop contract must forbid false wins: removing functionality, weakening tests, changing input distribution, loading all data when streaming is required, silently raising memory/thread budgets, skipping error paths, or using target-specific code outside approved targets. The AutoResearch CSV example shows why these constraints belong in the contract: an initial faster memory-mapped implementation violated the intended streaming-memory requirement. [Autoresearch CSV case](https://medium.com/@z1ad/how-i-used-autoresearch-to-make-my-c-csv-parser-10x-faster-in-1-hour-ed5b6e1e437c)

Known pipeline transitions—build, static analysis, correctness test, benchmark, comparison, report—remain deterministic. Use a model for hypotheses, code generation, and explanation only where it adds value; never let it skip a required check. This mirrors the fixed codegen/simulation/benchmark/report pipeline described in the Python-to-Rust article. [Fixed pipeline example](https://medium.com/loka-engineering/watching-a-python-to-rust-rewrite-was-painful-enough-to-build-this-fd3801ad02ba)

## Evidence, memory, and handoff

Keep experiment-specific commands, inputs, raw measurements, host details, and rejected hypotheses in `EVIDENCE.md` or `.harness/evidence/`, not `CONTEXT.md`. Canonical project memory may retain only a concise verified reusable fact: a benchmark command, approved constraint, source digest, accepted target, or measured lesson with its applicability condition. Never persist raw profiler logs, benchmark dumps, vendor claims, secrets, or a generic “always use SoA/SIMD/Rust” preference.

The handoff states what improved, the fixed workload, before/after samples, correctness/resource evidence, portability limits, rejected alternatives, and the next safe experiment. An optimization is complete when the approved target and all required correctness/resource gates pass; it does not authorize a deploy, rollout, or architecture rewrite.
