# Changelog

## 0.3.1 — concurrency and initialization hardening

Projects pinning the bundled runtime should re-run `upgrade_project.py --dry-run` to pick up this version.

### Fixed

- **Lost updates under concurrent readers (Windows):** `atomic_replace`/`atomic_delete` failed with `IO_ERROR [WinError 5]` when a rename raced a reader holding the target open. Both now retry transient share violations (WinError 5/32/33) with bounded backoff; atomicity is unchanged.
- **First-run initialization crash:** the writer-lock bootstrap validated `.harness` with a strict resolve before creating it, so every fresh project failed with `[WinError 2]`. Directory creation now precedes containment validation.
- **Fallback lock aliasing:** fallback writer locks keyed by unresolved paths let one file reached through different aliases (8.3 short names, subst drives, case variants, symlinks) acquire two independent locks. Lock keys are canonicalized via `realpath`, proven against both 8.3 aliases on NTFS and symlink aliases on Linux.
- **Unopenable lock files burned the contention timeout:** ACL/read-only lock files now fail fast as `LOCK_UNAVAILABLE`; byte-range contention keeps its bounded wait.
- **Memory eval harness:** M37 crashed on a missing `scripts["init"]` entry.

### Added

- Local oracles for memory evals M39 (identity-rebind and approval binding against git fingerprints, cross-project replay refusal), M40 (TTL/time/source-size/adapter-results/manifest bounds), and M41 (forget-restore truth, successor IDs, semantic-deletion honesty) — the eval matrix is now green on everything testable without a target model.
- `race_tests.py`: permanent two-process regression suite — contention against a held lock, patient commit exactly-once, crash-orphan recovery without manual cleanup, concurrent writer storm with torn-read detection, path-alias convergence, permission-denied lock open, identity/digest binding (input byte flip, Project ID flip, foreign root commit), exact run ownership including close-run idempotency and cross-run leak prevention, recall budget ceilings. Validated on Windows/NTFS and real Linux kernels (WSL2) at both privilege levels.
- `.github/workflows/ci.yml`: release gate running portability validation, the race suite, and memory evals on Ubuntu and Windows; eval failures are tolerated only for the not-yet-wired external-model oracles (M05/M06/M28/M31).

### Known-red by design

- Memory evals M05/M06/M28/M31 require a live target model; M34 requires a POSIX filesystem for symlink coverage.
