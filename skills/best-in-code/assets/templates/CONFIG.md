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
- Existing approval: reuse within unchanged scope; new material decisions require covering authorization
- Completion: finish authorized implementation and affected verification before final human acceptance

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

- Policy: current-only; adaptive routing requires an explicit user request or approved model plan
- User-pinned model/profile/effort wins: yes
- Primary model/effort: fixed per task; change only on explicit user request
- Authorized switch boundary: stable role/pass boundary only
- Mechanical delegation: authorized fast child for bounded work; primary model remains fixed
- Context boundary default: same-session
- Same-session rule: preserve confirmed actual model/effort for sequential non-independent work; never claim a cache hit
- Isolated-child rule: use a bounded role packet for cross-model/provider, independent, concurrent, resumed, or narrowed-context work
- Cache observation: UNKNOWN | REPORTED | UNAVAILABLE; advisory evidence only
- Cache hit, pricing, and retention prediction: prohibited
- Escalation: evidence-backed proposal; apply only within explicit model authorization
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
| automation.schedule | | one bounded interactive iteration and handoff | UNAVAILABLE |
| events.subscribe | | human-provided event and one bounded iteration | UNAVAILABLE |
| models.select | | current model with labeled pass | UNAVAILABLE |
| vcs.worktree | | sequential execution in current workspace | UNAVAILABLE |
| graph.ledger | bundled local runtime after Git/identity probe | manual Project Manager receipts | UNAVAILABLE |
| docs.versioned | | official docs/repo/local source | UNAVAILABLE |
| repository.remote | | local Git/official web/user evidence | UNAVAILABLE |
| browser.interactive | | E2E/manual evidence/Not verified | UNAVAILABLE |
| image.search | | official design sources/Not used | UNAVAILABLE |
| memory.semantic | | exact authoritative-store scan | UNAVAILABLE |
| evidence.static | | project checks/manual review | UNAVAILABLE |
| evidence.runtime | | focused local checks/Not verified | UNAVAILABLE |

## Local-only capability notes

Keep machine paths, credentials, account names, and private endpoints in ignored `.harness/local-capabilities.md`; never commit them to portable policy.
