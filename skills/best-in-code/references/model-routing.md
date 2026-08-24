# Adaptive Model Routing

Use this module only when the user requests model selection or `models.select` is `READY` with more than one verified model. Roles remain portable contracts; model names are provider bindings, not workflow states.

## Profiles

| Profile | Best fit | Default effort intent | Do not use as the sole authority for |
|---|---|---|---|
| `reasoning` | Material requirements, architecture, security/privacy, migrations, concurrency, performance/scale, difficult debugging, and deep final review | High; use higher settings only after representative evidence shows value | Ungated external/destructive decisions or deterministic test truth |
| `balanced` | Standard planning, implementation, integration, focused research, and ordinary QA | Medium; raise only for a measured reasoning bottleneck | A high-risk final review when a stronger isolated option is available |
| `fast` | Stable low-risk shards, mechanical edits, boilerplate, fixtures, documentation, and bounded evidence extraction | Low or medium | Architecture, ambiguous requirements, auth/security, migrations, production mutation, or final acceptance judgment |

For OpenAI GPT-5.6, after availability preflight, the example binding is `reasoning → gpt-5.6-sol`, `balanced → gpt-5.6-terra`, and `fast → gpt-5.6-luna`. This follows current official model positioning; re-check official documentation before changing a durable binding. Other providers map their own models to the same profiles.

## Scale-aware defaults

- `quick`: avoid switching overhead. Use the current model or one `fast` pass when the contract and focused verification are already stable.
- `standard`: use `balanced` by default. Escalate material planning or review to `reasoning`; delegate only stable, bounded, disjoint work to `fast`.
- `full`: use `reasoning` for requirements/architecture and high-risk or deep final review, `balanced` for implementation/integration, and `fast` only for well-specified low-risk shards.
- `review`: deterministic checks remain primary. Use `reasoning` for material risk review; a different model is not automatically isolated or independent.

The user may pin one model/profile/effort for the run or a pass. Preserve that choice unless unavailable or unsafe; report the limitation and ask before substituting when the exact model materially matters.

## Switching and handoff

1. Preflight the selector, exact model access, effort support, permissions, cost/quota boundary, and isolation. `Installed` or listed is not proof that a launch succeeded.
2. Route at a role/pass boundary, never in the middle of a mutation. Stabilize contracts and file ownership first.
3. Hand off only the bounded role packet: objective, exclusions, requirement/contract IDs, verified memory IDs, owned files, acceptance criteria, required checks, and stop condition. Do not forward the full chat, raw retrieval dumps, secrets, or unrelated context.
4. Record requested profile/model, preferred binding, actual model/effort, selection reason, isolation label, and fallback in `WORKFLOW.md`. The receiving pass confirms its actual runtime identity when the provider exposes it.
5. PM remains the only shared-state writer. Cross-model workers return packets and never race on `.harness/` or overlapping files.

An older current-layout project may not yet contain the model-routing sections from the latest templates. Do not require a schema migration for this additive feature: use this reference as the default and have PM append the compact model-routing ledger to the active `WORKFLOW.md` when routing first activates.

## Escalation and fallback

Escalate `fast → balanced → reasoning` only after classifying a failure as a reasoning/capability mismatch or when new risk changes the route. Do not retry the same prompt across models blindly, downgrade explicit high-quality routing to save cost, or bounce models within one pass. Deterministic evidence can invalidate any model's conclusion.

Fallback order: exact user-pinned available model → verified profile binding → current model with an appropriate supported effort → labeled same-model sequential pass. If selection is unavailable, continue truthfully where safe and never claim a switch occurred. A new paid service, credential, quota purchase, or materially higher cost uses the existing Decision Gate.
