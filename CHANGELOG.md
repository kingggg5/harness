# Changelog

## 0.5.0 — bounded Graph and Loop Engineering

### Added

- An optional, run-scoped `TASK-GRAPH.json` contract for real fan-out/fan-in, bounded evaluator loops, and human-gated consequential effects. It does not replace the canonical lifecycle graph, `STATE.json`, or `MEMORY.json`.
- A dependency-free fail-closed graph validator that rejects unknown fields, fake data edges, unbounded loops, hidden cycles, unsafe paths, unordered write conflicts, and consequential actions without a human approval edge.
- A reusable centralized-diamond example, graph invariant regression suite, CLI `graph-validate` command, router fixtures, and package checks.
- A 2026 research synthesis covering centralized coordination, the sequential-work penalty, context budgets, compiled knowledge layers, prompt-injection boundaries, and optional runtime adapters.
- A conditional execution-isolation contract for concurrent writers and long-running work: exact base revision, one worktree/workspace per writer, shared-resource allocation, one integration owner, status receipts, cancellation/stall detection, and fixed iteration/time/token/cost/failure limits.
- Portable `vcs.worktree` and `agents.supervise` capabilities with sequential/interactive fallbacks. Firstmate, Treehouse, GNHF, and No-Mistakes remain optional reviewed backends rather than dependencies.
- An optional dependency-free `graph-run` ledger with atomic claim/finish receipts, Project/Run/graph binding, exact Git baseline and ancestry checks, SHA-256 artifacts, commit diff containment by `write_scope`, bounded retry/loop transitions, timeout recovery, and fail-closed resume.
- Graph runtime integration tests covering real concurrent claims, human-gated fan-out, isolated worker commits, scope violations, artifact drift, stale recovery, and graph-digest tampering; stricter graph fixtures now cover safe artifact IDs, bounded lists, sound `join=any` inputs, and idempotency binding.
- A provider-neutral Loop Engineering contract and validator for turn, goal, scheduled, and proactive levels: trigger/dedupe/overlap rules, reproducible baseline and excluded scope, deterministic-first verification, fixed run/iteration/time/token/cost/external-call budgets, separate usage evidence, rollback binding, architecture/consequential human gates, and safe one-iteration fallbacks when supervision is unavailable.
- Loop-contract regression fixtures, a bounded performance example, current primary-source guidance for Codex/Claude long-running work, and explicit separation between the supervisor envelope, task graph, graph receipt ledger, lifecycle state, and durable memory.
- A shared bounded JSON loader for graph and loop control files, including duplicate-key rejection, link/hardlink refusal, descriptor identity checks, and size-capped reads. Malformed nested graph values now return validation errors instead of crashing.

### Changed

- Planner/Architect now performs Graph Engineering only when the work shape warrants it; it is not another mandatory agent. Strictly sequential and quick work remain single-owner by default.
- Task graphs with `max_parallel > 1` now require `provider-isolated` or `git-worktree` execution and an exact base commit; context isolation alone no longer qualifies concurrent writers as safe.
- Knowledge graphs remain a separate product decision for measured multi-hop, temporal, entity-resolution, and provenance needs; Harness does not create a duplicate generic `KNOWLEDGE.md`.
- Loop contracts now carry trusted verifier `command_id` values instead of executable argv. Backends must resolve IDs through reviewed read-only capability configuration and reject unknown IDs at execution time.
- GitHub Actions now use least-privilege tokens, immutable full-SHA action pins, non-persisted checkout credentials, package verification on both CI platforms, and a regression-tested fail-closed policy for expected memory-eval skips.

## 0.4.1 — portable release smoke install

### Fixed

- The Linux release job now resolves the packed archive to an absolute file path and invokes the installed launcher through Node directly, avoiding platform-specific npm bin-symlink permission and relative-package-spec behavior.

## 0.4.0 — release-ready package and reusable examples

### Added

- A tag-driven GitHub Release workflow that validates the deterministic core, verifies the exact npm package contents, smoke-installs the archive, and publishes the `.tgz` with `SHA256SUMS`.
- A fail-closed package gate that synchronizes npm, Codex, Claude, and Gemini versions; requires runtime, adapter, brand, and example files; rejects private or build-only files; and caps accidental package growth.
- Four copy-paste examples covering a quick bug fix, a full product feature, cross-model handoff, and read-only production review.
- A maintainer release checklist that keeps tagging deliberate and leaves npm-registry publication opt-in.

### Changed

- The npm archive now includes the README brand assets and examples so the packaged documentation is complete offline.

## 0.3.1 — concurrency and initialization hardening

Projects pinning the bundled runtime should re-run `upgrade_project.py --dry-run` to pick up this version.

### Fixed

- **Lost updates under concurrent readers (Windows):** `atomic_replace`/`atomic_delete` failed with `IO_ERROR [WinError 5]` when a rename raced a reader holding the target open. Both now retry transient share violations (WinError 5/32/33) with bounded backoff; atomicity is unchanged.
- **First-run initialization crash:** the writer-lock bootstrap validated `.harness` with a strict resolve before creating it, so every fresh project failed with `[WinError 2]`. Directory creation now precedes containment validation.
- **Fallback lock aliasing:** fallback writer locks keyed by unresolved paths let one file reached through different aliases (8.3 short names, subst drives, case variants, symlinks) acquire two independent locks. Lock keys are canonicalized via `realpath`, proven against both 8.3 aliases on NTFS and symlink aliases on Linux.
- **Unopenable lock files burned the contention timeout:** ACL/read-only lock files now fail fast as `LOCK_UNAVAILABLE`; byte-range contention keeps its bounded wait.
- **Memory eval harness:** M37 crashed on a missing `scripts["init"]` entry.
- **Approval/commit races:** migration now parses, archives, and CAS-checks one bounded byte snapshot; upgrade verifies the moved runtime against the approved exact snapshot before installing; initialization rollback also binds the exact generated runtime manifest.
- **Rollback recovery:** lifecycle operations hold one project writer lock through recovery. A changed failed runtime is preserved under `runtime-recovery` and the prior reviewed runtime is restored when safe; partial recovery reports `ROLLBACK_FAILED` with exact paths.
- **Wrong-repository recall:** recall now fails closed on Git root/remote/logical-scope mismatch instead of returning memory before write-time identity validation.
- **Canonical audit truth:** record, identity, tombstone, and transaction timestamps reject future skew; normal transaction IDs are recomputed; history links require reciprocal, same-tuple, acyclic relationships; tombstone scope must match its ID.
- **Derived-view dead end:** generated Markdown is a deterministic bounded projection with omission counts and a full-row digest, and `export-cache` rerenders the new revision so validation stays current.
- **Injection/secret bypasses:** expanded token-prefix and instruction/exfiltration heuristics; documentation now explicitly treats every recalled value as untrusted data after filtering.

### Added

- A conditional Business Analyst / requirements pass for unclear outcomes, actors, scope, business rules, stakeholder conflicts, and acceptance behavior. Quick work folds the check into PM; implementation-ready work skips it; no new state or human gate was added.
- A compact requirement baseline in `WORKFLOW.md`, BA-aware role packets and router fixtures, plus the optional `requirements.spec` capability. Existing repository conventions win; OpenSpec and GitHub Spec Kit are optional backends, never hard dependencies or automatic installs.
- An optional source-grounded `PROJECT-MAP.md` for complex-repository topology, domain vocabulary, module ownership, important flows, and external boundaries. `MEMORY.json` remains authority, `CONTEXT.md` remains generated, and no duplicate generic `KNOWLEDGE.md` is introduced.
- Provider-neutral adaptive model routing with `reasoning`, `balanced`, and `fast` profiles; OpenAI GPT-5.6 examples map to Sol, Terra, and Luna. User pins win, cross-model context is bounded, actual model/effort is recorded, and unavailable selection falls back truthfully without creating a false independent-QA claim.
- Local oracles for memory evals M39 (identity-rebind and approval binding against git fingerprints, cross-project replay refusal), M40 (TTL/time/source-size/adapter-results/manifest bounds), and M41 (forget-restore truth, successor IDs, semantic-deletion honesty) — the eval matrix is now green on everything testable without a target model.
- `race_tests.py`: permanent two-process regression suite — contention against a held lock, patient commit exactly-once, crash-orphan recovery without manual cleanup, concurrent writer storm with torn-read detection, path-alias convergence, permission-denied lock open, identity/digest binding (input byte flip, Project ID flip, foreign root commit), exact run ownership including close-run idempotency and cross-run leak prevention, recall budget ceilings. Validated on Windows/NTFS and real Linux kernels (WSL2) at both privilege levels.
- `.github/workflows/ci.yml`: release gate running portability validation, the race suite, and memory evals on Ubuntu and Windows; eval failures are tolerated only for the not-yet-wired external-model oracles (M05/M06/M28/M31).
- Python 3.12 is now the declared deterministic-core minimum so Windows junction checks are consistent across providers.

### Known-red by design

- Memory evals M05/M06/M28/M31 require a live target model; M34 requires a POSIX filesystem for symlink coverage.
