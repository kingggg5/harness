# Adaptive Mode Routing

Scale and operation are independent. Record `operation`, `requested_scale`, `selected_scale`, and `selection_reason` in `STATE.json`.

## Operations

| Operation | Meaning |
|---|---|
| `start` | Start a new delivery run. This is the default. |
| `resume` | Continue the one recorded next action of a validated unfinished run. |
| `review` | Return severity-ordered findings. |
| `init` | Non-destructive setup ([provider-adapters.md](provider-adapters.md)). |
| memory command | Direct memory operation ([memory-loop.md](memory-loop.md)); no delivery graph. |

An explicit operation wins. An unfinished run has a non-empty `run_id` and a state other than `DONE`; a freshly initialized blank state is not unfinished. Without an explicit operation, a clearly new task uses `start`; no new task, or a clear continuation of a validated unfinished run, uses `resume`. Resume keeps its selected scale unless new evidence requires escalation or the human changes it. `review` combines with any scale.

## Deterministic scale selection

1. An explicit `full`, `standard`, or `quick` selects that scale. Never downgrade explicit `full`.
2. With `auto`, select `full` when any full trigger applies.
3. Otherwise select `quick` only when every quick condition applies.
4. Otherwise select `standard`.

Full triggers: security, privacy, authentication/authorization, schema or data migration, concurrency correctness, production/external mutation, irreversible work, multi-service architecture, incident/release readiness, material dependency or supply-chain risk, performance/scale claims with a stated target (SLO, capacity or production load), unattended scheduled/event/proactive execution, or uncertainty that can change architecture or authorization.

Quick requires all of these: one bounded domain, unambiguous acceptance, low risk, no material external effect, no durable architecture/schema choice, and a deterministic focused verification path. A typo, isolated style correction, or proven one-file regression often qualifies.

Escalation is upward only. If explicit `quick` proves unsafe, stop before further material work and recommend a higher scale. Otherwise, when evidence changes the classification, record the trigger, escalate, keep valid completed work and continue from the current state.

## Optional graph, loop and requirements pass

- Task graph: never changes the selected scale; skip it for `quick`. Activation and shapes: [graph-engineering.md](graph-engineering.md).
- Loop contract: an ordinary internal retry needs none. `scheduled` and `proactive` loops need verified schedule/event and supervision capabilities; otherwise run one bounded interactive iteration and hand off. Details: [loop-engineering.md](loop-engineering.md).
- Business Analyst pass: runs inside `INTAKE` or `PLAN`, writes no shared state and adds no gate; in `quick`, PM does it inline. BA owns what/why; Planner owns how. Triggers: [requirements-analysis.md](requirements-analysis.md).

## Roles and gates

| Scale | Typical active roles | Human checkpoints |
|---|---|---|
| quick | PM, one applicable implementer, deterministic QA pass; BA folded into PM; Researcher/Designer only on trigger | Decision when material; final report; `WAITING_ACCEPTANCE` only when canonical state is used |
| standard | PM, Planner, applicable specialists, QA; BA/Researcher/Designer and task graph conditional | Concise plan checkpoint for material scope; conditional Design/Decision; Acceptance for delivery |
| full | PM, Planner, Researcher, every applicable specialist, isolated QA when available; BA and task graph still conditional | Bounded discovery when a material unknown blocks planning, Plan, conditional Design, Decision as needed, Acceptance for delivery |

Gates, like roles, activate only on need. The Design Gate triggers only for a new or changed visual direction, flow/information architecture, design system, motion contract, or third-party asset choice.

## Authorization and completion

Plan and Design checkpoints resolve material choices, not routine implementation details. A clear user request or an earlier approved requirement/design/model plan authorizes work within its scope; record it instead of asking again. A changed scope, unresolved material architecture/schema decision, breaking or destructive effect, new credential/paid-service use, production mutation, or external communication needs authorization that covers that specific action. Platform permission prompts do not substitute for product decisions.

Stop only for genuinely missing authority, a material unresolved choice, an explicit review boundary, or an evidence-backed blocker, not merely because a first implementation is ready.

## Review semantics

- `review quick`: one bounded artifact or diff and focused checks.
- `review standard`: ordinary repository/diff review with applicable domains.
- `review full`: release, incident, security/privacy, architecture, performance/scale, or explicitly deep audit.

A review ends with a findings handoff, not an Acceptance Gate, unless the user explicitly starts a remediation run.
