# Cross-Language Performance Engineering

Read this reference only when the requested outcome names latency, throughput, CPU, memory/RSS, allocation rate, startup time, battery/energy, I/O, scale, or a performance-sensitive rewrite. Language-specific tooling stays in the repository or an approved tool backend. A result counts only when the same behavior, input contract, error handling, and resource limits still pass.

## Start with a performance contract

Only when this lane is active, copy `.harness/runtime/assets/templates/PERFORMANCE-EVIDENCE.md` to `.harness/EVIDENCE.md` (or add its sections to an existing one) and fill it in. Also record the correctness corpus with its deterministic verifier, and the stop condition.

Record any unknown workload, baseline, or correctness check in the performance contract, then run one [discovery-loop.md](discovery-loop.md) cycle to establish it; never guess an optimization.

Init does not create a budget: copy `.harness/runtime/assets/templates/PERFORMANCE-BUDGET.json` to `.harness/PERFORMANCE-BUDGET.json` and fill it. The project benchmark emits baseline and candidate results in the `PERFORMANCE-RESULT.json` template shape. Validate each new result before storing or comparing it, then compare:

```bash
harness perf-validate --result .harness/evidence/perf-current.json --json
harness perf-check \
	--baseline .harness/evidence/perf-baseline.json \
	--current .harness/evidence/perf-current.json \
	--budget .harness/PERFORMANCE-BUDGET.json \
	--output .harness/evidence/perf-comparison-<iteration>.json \
	--json
```

`--output` refuses an existing file, so use a new name per iteration or omit it. Without the `harness` launcher on PATH, run `python -B .harness/runtime/scripts/performance_budget.py` (or `python -B <package>/skills/best-in-code/scripts/performance_budget.py`) with the same flags; `perf-validate` becomes `--validate --result <file> --json`.

The comparator only compares closed results; it never runs a benchmark. Benchmark execution and verifier registration belong to the project host under [loop-engineering.md](loop-engineering.md). A comparator PASS is evidence only and never authorizes merge, deploy, publish, or an architecture rewrite.

## Universal experiment sequence

1. **Baseline.** Run the fixed workload enough times to describe variance. Keep cold-start and warm-start results separate.
2. **Profile.** Identify the dominant cost: algorithmic work, data movement, allocation/GC, lock contention, branch misses, I/O, serialization, query plan, or external dependency.
3. **Hypothesize.** Change one causal factor and predict both the performance result and any correctness/resource risk.
4. **Implement.** Make the smallest reversible slice. Preserve public behavior and record any semantic trade-off explicitly.
5. **Verify.** Run the correctness corpus, negative/boundary cases, resource limits, and the same benchmark environment.
6. **Compare.** Keep only a repeatable improvement that meets the target without a material regression. Otherwise revert the loop-owned slice and record the result.

Never call a result "10x faster" from one warm microbenchmark. Randomize representative inputs where branch prediction or cache state could bias the result, report sample count and distribution, and distinguish emulator-relative comparisons from timing on real target hardware.

## Technique ladder

Use the lowest-risk technique the profiler evidence supports; each rung is a hypothesis to test, not a default. Guardrails by observed cost:

1. **Too much work:** preserve numeric precision, invalid-input handling, and the memory bound.
2. **Copies or allocations:** never retain borrowed/mutable data past its lifetime or introduce shared mutable state.
3. **Memory bandwidth or cache misses:** choose SoA only for hot-column scans; layout changes can affect ABI, serialization, cache invalidation, and readability.
4. **Dispatch or branch overhead:** keep necessary validation; never assume a branchless version is faster without measurement.
5. **Lock contention:** prove ordering, cancellation, idempotency, race freedom, and resource isolation.
6. **Vectorizable loop:** help the compiler vectorize and inspect the evidence before explicit SIMD; keep a portable scalar fallback and test every supported CPU/compiler target.
7. **I/O, database, network:** cache only with invalidation rules; never turn a benchmark cache into stale user-visible data or hide network failures.
8. **Language/runtime overhead:** a rewrite requires end-to-end evidence, a migration/operability plan, and a human Decision Gate.

## Writing style by runtime

Keep the product-facing API readable and isolate a proven hot kernel behind a small, testable boundary; add a reference implementation or property test when the optimized form is hard to inspect. Unsafe code, intrinsics, prefetch, cache warming, pools, custom allocators, and native extensions need target-specific profiler evidence, correctness tests, and a fallback, and stay out of ordinary application code; pools also need measured allocation pressure and explicit ownership/reset rules, and cache warming is never a startup ritual. Native code keeps overflow, alignment, aliasing, and lifetime checks. Dynamic runtimes first remove interpreter-level loops, conversions, serialization, and round trips. SQL and data workloads start from query plans, transfer volume, partition skew, and indexes; fuse transforms only when the engine preserves semantics and diagnostics. A cross-language rewrite needs a parity comparison (behavior, latency, memory, packaging, debugging, maintenance) on the same workload plus a Decision Gate; a headline speedup from another stack is not evidence.

## Parallelism

Parallelize only independent partitions with a bounded worker count, deterministic reduction/merge, controlled memory use, and an explicit contention model. Verify one worker through the maximum approved worker count; more threads can reduce performance through false sharing, cache pressure, synchronization, I/O saturation, or non-deterministic output. A parallel reduction must prove the same result and numerical tolerance as the serial reference.

## Bounded optimization loops

Use [loop-engineering.md](loop-engineering.md) only when repeated experiment/verify work is justified. Begin with one owner, `max_runs=1`, one fixed workload, and one rollback revision. Each iteration may make one hypothesis-driven change; keep/revert is based on deterministic correctness and comparable performance evidence.

The loop contract must forbid false wins: removing functionality, weakening tests, changing input distribution, loading all data when streaming is required, silently raising memory/thread budgets, skipping error paths, or using target-specific code outside approved targets.

Build, static analysis, correctness test, benchmark, comparison, and report stay deterministic. Use a model only for hypotheses, code generation, and explanation; never let it skip a required check.

## Evidence, memory, and handoff

Keep experiment-specific commands, inputs, raw measurements, host details, and rejected hypotheses in `.harness/EVIDENCE.md` or `.harness/evidence/`, not `CONTEXT.md`. Canonical project memory may retain only a concise verified reusable fact: a benchmark command, approved constraint, source digest, accepted target, or measured lesson with its applicability condition. Never persist raw profiler logs, benchmark dumps, vendor claims, secrets, or a generic "always use SoA/SIMD/Rust" preference.

The handoff states what improved, the fixed workload, before/after samples, correctness/resource evidence, portability limits, rejected alternatives, and the next safe experiment. An optimization is complete when the approved target and all required correctness/resource gates pass; it does not authorize a deploy, rollout, or architecture rewrite.
