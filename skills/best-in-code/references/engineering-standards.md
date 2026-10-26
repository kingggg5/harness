# Engineering Standards

Use this reference for nontrivial implementation or review decisions. Repository instructions and enforced toolchains remain authoritative; resolve material conflicts before a broad migration. UI work follows [frontend-skill-routing.md](frontend-skill-routing.md).

## Non-negotiable behavior

- Do not guess material requirements, credentials, production state, schema semantics, or external side effects. Investigate first; if uncertainty remains and changes the outcome, ask the human.
- Make no silent contract change and no duplicated implementation.

## Indentation and formatting

Use tabs in new projects and files where the language and enforced formatter permit. Where the repository or formatter uses spaces, keep spaces for scoped changes; add formatter config or propose a repository-wide migration only when asked. YAML uses spaces. Never mix tabs and spaces in one indentation regime.

## Correctness and maintainability

- Validate input at trust boundaries and make invalid states hard to represent.
- Define error ownership and propagation deliberately; do not swallow failures or leak sensitive details.
- Preserve public API, schema, stored-data, and configuration compatibility unless a breaking change is approved.
- Consider empty state, partial failure, retry, cancellation, timeout, cleanup, idempotency, ordering, and concurrency when relevant.
- Keep generated files, lockfiles, migrations, snapshots, and documentation aligned with the source change when they are genuinely affected.
- A named performance outcome uses [performance-engineering.md](performance-engineering.md); never claim a speedup without a comparable baseline and a passing correctness gate.

## Module and domain boundaries

When the interface itself is uncertain and the choice is material, compare placements of behavior: what the caller must know, where side effects live, how a public boundary can verify the contract, and how many unrelated callers must change. A useful module hides meaningful complexity behind a small interface; a wrapper that merely moves the same dependencies adds no value. Architecture work starts from a concrete missing seam or change cost, not a general urge to deepen every module.
