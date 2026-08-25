# Harness Configuration

- Schema version: 2
- Project ID:

## Routing defaults

- Default operation: start
- Default scale: auto
- Explicit full may be downgraded: no
- Auto-resume validated unfinished run: when no new task or a clear continuation
- Discovery no-progress limit: 2
- Same-blocker attempt limit: 3

## Gates

- Quick: decision when material; acceptance summary for delivery
- Standard: concise plan checkpoint when material; conditional design/decision; acceptance for delivery
- Full: plan; conditional design; decision when material; acceptance for delivery
- Review: findings handoff; no delivery Acceptance Gate
- Design trigger: changed visual direction, flow/information architecture, design system, motion contract, or third-party assets

## Memory

- Authoritative project store: `.harness/MEMORY.json`
- Recall ceiling: 20 records and 12000 UTF-8 bytes
- Global store: `$HARNESS_HOME/MEMORY.json` or `~/.harness/MEMORY.json`
- Derived views: `CONTEXT.md`, `PREFERENCES.md`, `DECISIONS.md`
- Project map: optional; activate only for reusable complex-repository knowledge
- Semantic adapter: none
- Semantic cache root: `.harness/.cache/memory`
- Semantic cache is canonical: no

## Model routing

- Policy: adaptive when `models.select` is ready; current model otherwise
- User-pinned model/profile/effort wins: yes
- Switch boundary: stable role/pass boundary only
- Escalation order: fast → balanced → reasoning, only on evidence or changed risk
- Full-chat cross-model handoff: prohibited

| Profile | Intended work | Preferred backend/model | Default effort | Fallback |
|---|---|---|---|---|
| reasoning | Material planning, architecture, high-risk/deep review | | high | current model, limitation recorded |
| balanced | Standard implementation, integration, ordinary QA | | medium | current model |
| fast | Stable low-risk bounded shards | | low or medium | balanced/current model |

## Capability bindings

Leave backend blank until preflight proves it ready. Do not treat installation as readiness.

| Capability ID | Preferred backend | Fallback | State |
|---|---|---|---|
| agents.parallel | | sequential role passes | UNAVAILABLE |
| agents.isolated | | labeled self-review | UNAVAILABLE |
| agents.supervise | | one bounded interactive iteration | UNAVAILABLE |
| models.select | | current model with labeled pass | UNAVAILABLE |
| vcs.worktree | | sequential execution in current workspace | UNAVAILABLE |
| docs.versioned | | official docs/repo/local source | UNAVAILABLE |
| repository.remote | | local Git/official web/user evidence | UNAVAILABLE |
| browser.interactive | | E2E/manual evidence/Not verified | UNAVAILABLE |
| image.search | | official design sources/Not used | UNAVAILABLE |
| memory.semantic | | exact authoritative-store scan | UNAVAILABLE |
| evidence.static | | project checks/manual review | UNAVAILABLE |
| evidence.runtime | | focused local checks/Not verified | UNAVAILABLE |

## Local-only capability notes

Keep machine paths, credentials, account names, and private endpoints in ignored `.harness/local-capabilities.md`; never commit them to portable policy.
