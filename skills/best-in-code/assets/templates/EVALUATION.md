# Harness Evaluation Run

Use only when benchmarking Harness or comparing models/providers.

- Schema version: 1
- Memory revision: 0
- Fixture ID:
- Repository revision:
- Model/provider/effort:
- Tool/capability profile:
- Fixed acceptance criteria:
- Cache telemetry source and coverage (`REPORTED` / `UNAVAILABLE` / `UNKNOWN`):

| Metric | Result | Evidence/method |
|---|---|---|
| Acceptance criteria passed | | |
| Required state/gates matched | | |
| Selected-memory digest | | |
| Verification autonomy | | |
| Canonical input/output tokens | | |
| Cache-read input tokens (if reported) | | |
| Cache-creation input tokens (if reported) | | |
| Cache telemetry coverage (reported / applicable observations) | | |
| Cache-read share (ppm; only with full coverage) | | |
| Cost as reported | | |
| Elapsed time | | |
| Human interventions | | |
| Defect-loop count | | |
| Unrelated diff/entropy | | |
| Security or memory incidents | | |
| Fabricated evidence claims | | |

`input_tokens` is Harness's canonical total input after adapter normalization. `cached_tokens` is the legacy alias for cache-read input tokens; when the paired read/creation counters are reported, they are disjoint subsets of canonical input. Record the pair only when the provider reports both faithfully; otherwise write `UNAVAILABLE`, not `0`; use `UNKNOWN` when no trustworthy result was retained. Cache-read share is `floor(read * 1,000,000 / input_tokens)` and is unavailable when coverage is incomplete or input is zero. It is not a cache-hit, pricing, retention, or re-read-waste claim.
