# Portable Capability Contract

Harness depends on capabilities, not vendor or model names. At intake, add a preflight row only for an optional capability the run depends on; core file and shell access need none. Record its actual backend, permissions, isolation, version when material, and state: `READY`, `DEGRADED`, `UNAVAILABLE`, or `DIRTY`.

## Capability IDs

Self-explanatory: `agents.parallel`, `human.ask`, `filesystem.read` / `filesystem.write`, `shell.execute`, `repository.local` / `repository.remote`, `web.search` / `web.fetch`, `browser.interactive`.

| ID | Purpose |
|---|---|
| `agents.isolated` | Verify with context and ownership isolated from implementation. |
| `agents.supervise` | Observe, cancel, and reconcile bounded long-running workers without continuous model polling. |
| `automation.schedule` | Wake a bounded run on a verified cadence with status, pause/cancel, overlap, expiry, and run-count controls. |
| `events.subscribe` | Receive authenticated bounded events with target validation, replay protection, and deduplication. |
| `models.select` | Launch a verified model/effort profile for a bounded role pass. |
| `decision.semantic` | Bounded typed recommendations for route, risk, retrieval, or guardrail checks. |
| `docs.versioned` | The vendor's own docs MCP for that vendor, then a version-aware backend such as Context7; official docs, repository or local source as fallback. |
| `vcs.worktree` | One isolated version-control workspace per concurrent writer, safely retired. |
| `graph.ledger` | Persist node claims, receipts, artifact digests, and resume checks without executing nodes. |
| `image.search` | Public visual references with domain/source controls. |
| `memory.semantic` | Scoped candidates from a semantic index (see MemPalace below). |
| `requirements.spec` | Repository-native requirement/spec artifacts from an approved baseline. |
| `evidence.static` / `evidence.runtime` | Deterministic static or runtime evidence. |
| `evidence.sources` | Read-only crash, error, ticket, usage or business data catalogued in `.harness/SOURCES.json` ([evidence-sources.md](evidence-sources.md)). |

Tool and skill names are backend bindings, for example the Claude Code subagents `harness-qa`/`harness-researcher` (`agents.isolated`), GitHub (`repository.remote`), Exa (`web.search`), OpenSpec or GitHub Spec Kit (`requirements.spec`) and ShipProof (`evidence.static`). Never require or claim a named backend when only the capability matters.

**MemPalace for `memory.semantic`.** Installed is not ready: preflight executable/version, UTF-8 output, explicit palace path, status, a Project-ID wing and one safe scoped query. Never auto-install or mine home/parent directories, conversations, archives, or raw logs. Index only the sanitized output of `memory_ops.py export-cache` (dry-run the mine step) and use scoped search with a small result limit. A result lacking matching Project ID, canonical ID, source revision, and digest is only a lead. Never claim an index rebuild or negative search succeeded without recorded evidence from those external commands.

## Fallback order

| Need | Fallback order |
|---|---|
| Role execution | Parallel isolated agent → sequential isolated session → fresh-session review → labeled same-agent pass |
| Concurrent writer workspace | Verified provider-isolated workspace → native Git worktree → sequential execution in one workspace |
| Long-running supervision | Event-driven supervisor with status/cancel/stall detection → one bounded interactive iteration → handoff |
| Scheduled/event loop | Verified scheduler/subscription with dedupe and cancellation → one bounded interactive iteration → reusable handoff command |
| Durable graph receipts | Bundled local Git-backed ledger → Project Manager records the same evidence manually in `WORKFLOW.md` → static graph only |
| Typed decision | Bundled deterministic decision runtime → labeled policy rule → human decision for material uncertainty |
| Current documentation | Versioned-doc tool → official versioned docs → official repository/tag → installed local source → ask human |
| Remote repository | Connector → local Git → official web source → user-provided evidence |
| Real-user evidence | Catalogued read-only source → export or dashboard the human provides → one-sided conclusion labeled as such |
| Browser/UI verification | Browser automation → repository E2E → manual screenshot/walkthrough evidence → `Not verified` |
| Semantic memory | Scoped memory adapter → exact scan of canonical `.harness/` files → ask human |
| Requirement/spec artifacts | Existing repository convention → compact Harness baseline → approved optional spec backend → human clarification |
| Human question | Interactive question tool → set `WAITING_DECISION` and return a gate packet |
| File mutation unavailable | Return a patch/artifact and state that it was not applied |
| Static audit | Selected trusted auditor → project linters/scanners → targeted manual review → `Not verified` |

The outcome must remain truthful under every fallback; a missing capability never permits invented results.

## Preflight record

For each selected capability record:

| Capability | Backend | Version/revision | Permission | Isolation | State | Fallback/limitation |
|---|---|---|---|---|---|---|

Installed is not the same as ready. Probe the smallest safe operation and verify output encoding, authentication/status when applicable, scope, and target project. Do not auto-install, connect an account, expand permissions, or mutate external state merely to improve a capability.

## Isolation language

Report labels map one-to-one to the role-packet labels in [model-routing.md](model-routing.md) and `assets/templates/ROLE-PACKET.md`:

- `independent QA` = `independent-review`: different isolated context and no implementation ownership.
- `isolated review` = `isolated`: isolated context, independence from implementation stated.
- `self-review` = `same-context`: same agent or same implementation context.
- `deterministic verification`: tools/tests with reproducible inputs, regardless of reviewer isolation.

Never substitute one label for another.
