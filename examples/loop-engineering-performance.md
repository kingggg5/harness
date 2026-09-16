# Bounded performance loop

This example improves one measured checkout workload without turning “keep optimizing” into an unlimited agent run.

1. Copy `loop-engineering-performance.json` to `.harness/LOOP-CONTRACT.json`.
2. Replace the Project ID, Run ID, rollback revision, baseline, excluded scope, paths, trusted verifier IDs, and approved budgets with repository evidence.
3. Capture the baseline under the same workload and environment used by the verifier.
4. Copy `.harness/runtime/assets/templates/PERFORMANCE-EVIDENCE.md` to `.harness/EVIDENCE.md` and record the dataset/input digest, sample count, host/runtime, cold/warm state, latency/RSS target, correctness corpus, and resource caps.
5. Copy `PERFORMANCE-RESULT.json` and `PERFORMANCE-BUDGET.json` from the pinned runtime templates, then emit baseline/current results through the project benchmark and compare them with `harness perf-check --baseline ... --current ... --budget ... --json`.
6. Run `harness loop-validate --contract .harness/LOOP-CONTRACT.json`.
7. Let one owner make one hypothesis-driven change per iteration. Keep a candidate only when deterministic correctness and budget checks pass against comparable runs.
8. Reject false wins: changed input distribution, removed feature/error path, weaker verifier, silent higher memory/thread cap, or target-specific code outside the approved target set.
9. Stop after the first terminal condition. Push, merge, and deploy remain human-gated even when the performance target passes.

Begin with `max_runs=1` against one representative workload. Review the quality and usage receipt before increasing cadence, scope, concurrency, or model cost.

Configure the two example IDs in the backend's human-reviewed verifier registry: `performance-budget` may run the fixed project benchmark followed by `harness perf-check --baseline ... --current ... --budget ...`, and `checkout-regression` may run the focused test suite. Keep executable paths and fixed arguments in that trusted registry, not in `LOOP-CONTRACT.json`; reject an ID that is absent or maps to a write-capable command.

Use a task graph inside the loop only when an iteration truly splits into independent work. Do not parallelize multiple performance edits against the same files or benchmark environment.
