# Execution Isolation and Long-Running Work

Use this reference only for concurrent writers, work that must survive a session boundary, or a bounded autonomous loop. It defines an execution envelope with one owner, exact baselines, separate workspaces, observable progress, and safe cleanup. It does not authorize agent spawning, pushing, merging, installing tools, or unattended external effects.

## Activation and fallback

- One writer or a strictly sequential chain: use the current workspace and one owner. Do not create worktrees for ceremony.
- Concurrent read-only research: isolated context is sufficient when no shared mutable tool state is involved.
- Concurrent writers: require `agents.parallel`, `agents.isolated`, and a verified workspace-isolation backend such as `vcs.worktree`. Otherwise execute the same graph sequentially.
- Long-running work: require a validated `.harness/LOOP-CONTRACT.json` from [loop-engineering.md](loop-engineering.md) and a supervisor that can report current state, cancel, and detect a stalled worker. Otherwise run one interactive iteration and hand back the next command.

Worktrees isolate checked-out files, `HEAD`, and the index. They are not security sandboxes: Git objects and many refs/config values remain shared, while databases, ports, package caches, credentials, external services, and processes may still collide. Allocate those resources explicitly or serialize the affected nodes.

## Execution envelope

Before dispatch, Project Manager records:

| Field | Required value |
|---|---|
| Objective and exclusions | One bounded outcome and named non-goals |
| Baseline | Exact source revision plus dirty-state disposition; never absorb unrelated human changes |
| Ownership | One branch/workspace and one write owner per node |
| Resource isolation | Ports, temporary paths, database/schema, caches, credentials and external targets |
| Verification | Focused command, full applicable gates, and evidence location |
| Budgets | Parallel workers, iterations, transitions, elapsed time, tokens/cost, failures and external calls |
| Supervision | Status/receipt channel, heartbeat or stall deadline, cancel path and cleanup owner |
| Authority | Actions allowed automatically and the exact human-gated boundaries |

The role packet carries the concrete workspace, base revision, branch, budgets, and status channel. The task graph records only the portable isolation strategy and exact base revision; local absolute paths stay in ignored capability notes.

## Native Git worktree protocol

Prefer native Git when it is already available and enough for the project:

1. Verify the repository root, exact base commit, source worktree status, existing linked worktrees, intended branch name, and destination containment. Do not stash, reset, relocate, or absorb existing user changes automatically.
2. Create one unique branch/worktree per concurrent writer from the recorded base. Never use force to reuse a branch/path whose ownership is unclear.
3. Give the worker only its assigned worktree and write scope. Shared services and generated outputs still need separate names/ports or serialization.
4. The worker commits a bounded result and returns commit ID, base ID, diff summary, commands, evidence, residual risk, and cleanup readiness. It does not push, merge, rebase another branch, or delete the worktree unless explicitly assigned and authorized.
5. Project Manager verifies ancestry and expected files, integrates through one owned branch, resolves conflicts against the approved contract, and runs post-merge QA. A worker pass is not proof that the integrated result works.
6. Remove only a clean, verified, owned worktree using normal Git lifecycle operations. Never force-remove a dirty/locked/unknown tree. Preserve it and ask the human when evidence or changes remain.

Use machine-readable `git worktree list --porcelain -z` for automation. Prefer normal `git worktree remove`; it refuses dirty trees unless forced, and that refusal must be respected.

## Bounded long-running loop

An unattended label such as “overnight” never means unlimited. The validated loop contract, iteration steps and budgets live in [loop-engineering.md](loop-engineering.md). Inside an isolated workspace, a failed iteration restores only the worker-owned slice through a recoverable operation; never reset shared/user work, keep a failing partial change, rewrite the objective, weaken a gate, or convert a timeout into a pass. When safe restoration is uncertain, preserve the worktree and escalate.

The supervisor treats event logs as history, not current truth. It checks worker/process liveness, last verified progress, branch/worktree identity, budget usage, pending human decisions, and external waits. A stale worker is inspected once, then cancelled or escalated at the declared deadline; it is not relaunched indefinitely. The [loop runtime ledger](loop-runtime.md) can invalidate and continue/block/cancel an outer iteration lease; the [graph runtime ledger](graph-runtime.md) can requeue/fail/block an inner node lease. Neither can stop the underlying process or remove its workspace. Finish as `PASS_WITH_EVIDENCE`, `CONDITIONAL`, `BLOCKED`, `BUDGET_EXHAUSTED`, `NO_PROGRESS`, or `CANCELLED`.

Push, PR creation, merge, deploy, publish, payment, deletion, permission changes, paid calls, and production mutation retain their normal human gates. Successful tests are evidence, not authorization.

## Human-readable planning artifact

A plan may be rendered as Markdown or local HTML when a visual dependency/UX review materially improves human judgment. The rendered artifact is a derived view: keep scripts inactive, escape untrusted text, disclose source provenance, and treat annotations as feedback. Project Manager normalizes accepted annotations back into the authoritative `WORKFLOW.md`/task graph and obtains the normal Plan or Decision approval before execution.

## Optional backend routing

Harness adopts contracts, not tool brands. Do not install these automatically:

| Backend | Consider only when | Keep outside its authority |
|---|---|---|
| Native Git worktree | A few concurrent writers and simple lifecycle needs | Agent/process sandboxing, shared-service isolation, merge approval |
| Provider-isolated workspace | The provider proves separate filesystems and exact base revision | Claims of independence without capability evidence |
| External worktree pool, loop runner, pre-push gate or fleet coordinator | A measured setup, iteration or supervision bottleneck remains | Security sandboxing, unlimited runs, push/merge/release authority, human intent decisions, destructive cleanup, or external-write consent |

Before adopting an external backend, apply [skill-supply-chain.md](skill-supply-chain.md) and pin an approved version or commit; also verify its Windows/Linux support, resource bounds, rollback, and deterministic tests.

## Research basis

The dated evidence behind this design (checked August 2026) lives in [research-basis-2026.md](research-basis-2026.md#execution-isolation); read it only when changing this policy.

