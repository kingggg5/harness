# Adaptive Mode Routing

Scale and operation are independent. Record `operation`, `requested_scale`, `selected_scale`, and `selection_reason` in `STATE.json`.

## Operations

| Operation | Meaning |
|---|---|
| `start` | Start a new delivery run. This is the default. |
| `resume` | Validate project identity and state, then continue the one recorded next action. |
| `review` | Keep implementation roles read-only and return severity-ordered findings. |
| `init` | Create missing canonical files and approved provider adapters without overwriting existing content. |
| memory command | Run the lightweight memory protocol without the delivery graph. |

An explicit operation wins. An unfinished run means `run_id` is non-empty and state is not `DONE`. With no explicit operation: a request containing a clearly new task uses `start`; no new task plus a validated unfinished run uses `resume`; a request that clearly continues the active objective also uses `resume`. If the new request and active run overlap ambiguously, ask whether to resume or start rather than replacing state silently. A freshly initialized blank state is not unfinished. `review` may combine with any scale. Resume retains its selected scale unless new evidence requires escalation or the human explicitly changes it.

## Deterministic scale selection

1. An explicit `full`, `standard`, or `quick` selects that scale. Never downgrade explicit `full`. If explicit `quick` is unsafe, pause and recommend escalation before material work.
2. With `auto`, select `full` when any full trigger applies.
3. Otherwise select `quick` only when every quick condition applies.
4. Otherwise select `standard`.

Full triggers: security, privacy, authentication/authorization, schema or data migration, concurrency correctness, production/external mutation, irreversible work, multi-service architecture, incident/release readiness, material dependency or supply-chain risk, performance/scale claims, or uncertainty that can change architecture or authorization.

Quick requires all of these: one bounded domain, unambiguous acceptance, low risk, no material external effect, no durable architecture/schema choice, and a deterministic focused verification path. A typo, isolated style correction, or proven one-file regression often qualifies.

Standard covers normal multi-file bugs and features, cross-component work, and product changes without a full trigger.

Escalate only upward when evidence changes the classification. Record the trigger and continue from the current state; do not discard valid completed work.

## Task-graph routing

Graph Engineering does not change the selected scale. Activate the optional per-run task graph only when one of these is true: the human explicitly requests it; two or more jobs can run independently after a stable contract and later fan in; the work crosses meaningful module/service ownership; a clear deterministic rubric justifies a bounded evaluator loop; or an expensive-to-undo effect needs an explicit human predecessor.

Skip it for `quick`, a strictly sequential migration or reasoning chain, or a tool-dense task where every worker needs the same evolving context. Use a single-owner chain in those cases. For an active graph choose the smallest shape from [graph-engineering.md](graph-engineering.md), cap concurrency and transitions, and validate `.harness/TASK-GRAPH.json` before scheduling nodes.

## Requirements-pass routing

Trigger the Business Analyst pass when one material item is unresolved: business outcome, primary actor or stakeholder, in/out scope, source of a business rule, conflict between stakeholders or requirements, observable acceptance behavior, or a high-impact workflow such as payment, approval, permissions, regulated processing, or an external integration. Inspect repository evidence first; do not turn discoverable facts into human questions.

Skip the pass for an implementation-ready bug, refactor, copy/style fix, or technical task with an approved contract and testable acceptance criteria. In `quick`, PM performs any tiny requirements check inline. In `standard`, run the pass only on trigger. In `full`, keep the pass conditional but isolate it when stakeholder or rule complexity makes independent analysis useful.

The pass runs within `INTAKE` or `PLAN`, writes no shared state, and adds no gate. It returns a compact requirement baseline to PM. BA owns **what/why** and unresolved business intent; Planner/Architect owns **how** and technical contracts. Requirement decisions use the existing Plan or Decision checkpoint.

## Roles and gates

| Scale | Typical active roles | Human checkpoints |
|---|---|---|
| quick | PM, one applicable implementer, deterministic QA pass; BA folded into PM; Researcher/Designer only on trigger | Decision when material; Acceptance summary for delivery |
| standard | PM, Planner, applicable specialists, QA; BA/Researcher/Designer and task graph conditional | Concise plan checkpoint for material scope; conditional Design/Decision; Acceptance for delivery |
| full | PM, Planner, Researcher, every applicable specialist, isolated QA when available; BA and task graph still conditional | Bounded discovery, Plan, conditional Design, Decision as needed, Acceptance for delivery |

Do not activate a role or gate merely because its row exists. The Design Gate triggers only for a new or changed visual direction, flow/information architecture, design system, motion contract, or third-party asset choice.

## Review semantics

- `review quick`: one bounded artifact or diff and focused checks.
- `review standard`: ordinary repository/diff review with applicable domains.
- `review full`: release, incident, security/privacy, architecture, performance/scale, or explicitly deep audit.

Review never authorizes implementation, external mutation, hidden cleanup, or durable-memory mutation. It ends with a findings handoff rather than an Acceptance Gate unless the user explicitly starts a remediation run. A same-agent review is labeled `self-review`; only isolated context and ownership may be labeled `independent QA`.
