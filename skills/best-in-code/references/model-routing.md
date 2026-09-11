# Adaptive Model Routing

Use this module when the user requests model selection, an adaptive multi-model workflow, or a cross-model handoff. Available models alone do not activate routing. Choose the primary model and effort once per task and preserve them unless the user explicitly requests a change. Roles remain portable contracts; model names are provider bindings, not workflow states.

## Profiles

| Profile | Best fit | Default effort intent | Do not use as the sole authority for |
|---|---|---|---|
| `reasoning` | Material requirements, architecture, security/privacy, migrations, concurrency, performance/scale, difficult debugging, and deep final review | High; use higher settings only after representative evidence shows value | Ungated external/destructive decisions or deterministic test truth |
| `balanced` | Standard planning, implementation, integration, focused research, and ordinary QA | Medium; raise only for a measured reasoning bottleneck | A high-risk final review when a stronger isolated option is available |
| `fast` | Stable low-risk shards, mechanical edits, boilerplate, fixtures, documentation, and bounded evidence extraction | Low or medium | Architecture, ambiguous requirements, auth/security, migrations, production mutation, or final acceptance judgment |

Provider adapters bind these profiles to verified available models. Treat existing model names as examples rather than a current ranking; check provider documentation when choosing a new binding. No profile overrides an explicit user choice.

## Initial selection and authorized child routing

- `quick`: preserve the current model and effort for the task.
- `standard`: when initial selection is requested, consider `balanced` for ordinary work.
- `full` or `review`: when initial selection is requested, consider `reasoning` for material planning and risk review. Deterministic checks remain primary.

These are selection hints, not mid-task switching instructions. An authorized fast sub-agent may handle bounded mechanical work such as renaming, formatting, summarization, or scraping while the primary retains planning, security decisions, and integration. Other cross-model role routing requires an explicit user request or an already approved model plan. If a required model becomes unavailable, report the limitation and obtain a choice before substituting it.

## Context boundary and cache observation

Choose a context boundary for every routed pass. A profile selects capability; it does not decide whether a pass inherits context or is isolated.

| Boundary | Packet context-isolation label | Use when | Context transfer | Cache rule |
|---|---|---|---|---|
| `same-session` | `same-context` | Sequential work needs the same verified context and does **not** claim independent review | Continue the current session with the confirmed actual model and effort. A model or effort change starts a new boundary. | It may preserve provider continuity, but never promise a cache hit, price, or lifetime. |
| `isolated-child` | `isolated`, or `independent-review` with independently scoped review evidence | A pass crosses model/provider, needs an independent review, runs concurrently, resumes after a context reset, or needs a narrower permission/context envelope | Send only the bounded role packet. Treat the receiving context as new. | Treat reuse as unavailable unless the receiving runtime independently reports it. Never infer reuse across providers or children. |

The Role Packet is valid only when those fields form one row of this crosswalk: `same-session` / `same-context` / `current-session`, or `isolated-child` / (`isolated` or `independent-review`) / `bounded-role-packet`. These are context/review labels, not a claim that checkouts, services, credentials, or other mutable resources are isolated. A different model or provider never establishes `independent-review` by itself.

Record one advisory cache observation with the pass: `UNKNOWN` when no trustworthy observation was requested or retained, `REPORTED` when the provider/runtime exposes attributable counters, and `UNAVAILABLE` when that interface cannot expose them. Missing telemetry is not zero. A reported zero is still `REPORTED`, while a cache hit/miss, timing, price, or retention lifetime is never predicted from the policy. Cache observation may inform a later human routing decision; it never overrides quality, isolation, budget, or acceptance evidence.

## Switching and handoff

1. Preflight the selector, exact model access, effort support, permissions, cost/quota boundary, context boundary, and isolation. `Installed` or listed is not proof that a launch succeeded.
2. Confirm that the user requested the change or already approved this model plan. Route only at a stable role/pass boundary, never in the middle of a mutation. Stabilize contracts and file ownership first.
3. Prefer `same-session` for a sequential continuation that needs shared context. Preserve its confirmed actual model and effort; do not switch models merely to chase an unverified cache outcome.
4. Use `isolated-child` for a cross-model/provider or independent pass. Hand off only the bounded role packet: objective, exclusions, requirement/contract IDs, verified memory IDs, owned files, acceptance criteria, required checks, stop condition, and any approved evidence locations. Do not forward the full chat, raw retrieval dumps, secrets, or unrelated context.
5. Record requested profile/model, preferred binding, actual model/effort, selection reason, context boundary, transfer mode, cache observation/evidence, context-isolation label, and fallback in `WORKFLOW.md`. The receiving pass confirms its actual runtime identity when the provider exposes it.
6. PM remains the only shared-state writer. Cross-model workers return packets and never race on `.harness/` or overlapping files.

An older current-layout project may not yet contain the model-routing sections from the latest templates. Do not require a schema migration for this additive feature: use this reference as the default and have PM append the compact model-routing ledger to the active `WORKFLOW.md` when routing first activates.

## Escalation and fallback

When evidence shows a capability mismatch, diagnose it and propose a better route. Keep the primary model/effort fixed until the user requests the change; an already approved child-model plan may govern child escalation. Do not retry the same prompt across models blindly. Deterministic evidence can invalidate any model's conclusion.

If optional selection is unavailable, continue with the current model and effort where the task permits, using labeled sequential passes. Do not silently substitute an explicitly required model. A new paid service, credential, quota purchase, or materially higher cost outside existing authorization uses the Decision Gate.
