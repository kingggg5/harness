# Bounded performance loop

This example improves one measured checkout workload without turning “keep optimizing” into an unlimited agent run.

1. Copy `loop-engineering-performance.json` to `.harness/LOOP-CONTRACT.json`.
2. Replace the Project ID, Run ID, rollback revision, paths, commands, and approved budgets with repository evidence.
3. Capture the baseline under the same workload and environment used by the verifier.
4. Run `harness loop-validate --contract .harness/LOOP-CONTRACT.json`.
5. Let one owner make one hypothesis-driven change per iteration. Keep a candidate only when deterministic correctness and budget checks pass against comparable runs.
6. Stop after the first terminal condition. Push, merge, and deploy remain human-gated even when the performance target passes.

Use a task graph inside the loop only when an iteration truly splits into independent work. Do not parallelize multiple performance edits against the same files or benchmark environment.
