# Performance Evidence

Use this only for a task with a named performance or scale outcome. Keep raw profiler output and large benchmark artifacts under `.harness/evidence/`; record their paths and digests here.

## Contract

- Objective and user-visible outcome:
- Excluded behavior and incompatible optimizations:
- Target metric and threshold:
- Correctness/resource gates:
- Approved iteration, elapsed-time, thread/concurrency, memory, and cost limits:
- Rollback revision and owned paths:

## Workload and environment

- Dataset/input generator, size, distribution, seed, and digest:
- Baseline revision:
- Command/verifier ID:
- Runtime/compiler/database and build flags:
- Host/CPU/OS/container details:
- Cold/warm state and sample count:

## Baseline

| Metric | Samples | p50 | p95/p99 | Mean | RSS/heap | CPU/I/O | Evidence path/digest |
|---|---|---|---|---|---|---|---|
| | | | | | | | |

## Experiments

| Iteration | One hypothesis | Changed files | Correctness result | Performance result | Keep/revert | Limitations |
|---|---|---|---|---|---|---|
| | | | | | | |

## Final comparison

| Metric | Baseline | Candidate | Change | Acceptance status |
|---|---|---|---|---|
| | | | | |

- Input/output compatibility verified:
- Boundary, error, cancellation, ordering, and concurrency checks:
- Portability/hardware caveats:
- Rejected hypotheses and why:
- Human decision required or `N/A`:
