# Bounded Discovery Loop

Read this reference when a bug, performance, scale, architecture, security, incident, or material unknown must be understood before planning. Discovery reduces uncertainty; it does not become an unbounded research phase or authorize implementation.

## Activation

Run one concise pass when a material unknown blocks planning. Standard may use a single targeted pass; quick skips discovery when repository evidence already makes the change and verification path unambiguous. Repeat only when a new material unknown could change requirements, architecture, risk, workload, cost, acceptance criteria, or the responsible role.

Use the relevant lane:

- **Bug:** reproduce the failure, identify expected versus actual behavior, map the affected path and blast radius, then form one root-cause hypothesis.
- **Performance:** set the contract in [performance-engineering.md](performance-engineering.md) before choosing an optimization; this loop resolves its unknowns.
- **Scale:** convert product usage into concurrency, requests, bytes, database/queue work, and failure scenarios. Keep workload assumptions explicit and separate estimates from measured throughput.
- **Architecture/security:** map trust, ownership, data, side-effect, deployment, and recovery boundaries; identify the invariant that evidence must prove.

## Discovery contract

For a `.harness` delivery run or a multi-cycle investigation, record the compact contract in `WORKFLOW.md` and detailed lane evidence in conditional `EVIDENCE.md` before probing:

- objective and excluded scope;
- known facts, assumptions, and open questions;
- reproduction or baseline command and evidence location;
- read-only boundary and actions that require approval;
- maximum cycles, elapsed time, cost, and external calls;
- plan-readiness and stop conditions.

Otherwise state the objective, read-only boundary, and stop condition inline.

Profiling untrusted code, fuzzing, DAST, load tests, production traffic, external targets, credentials, paid services, and installations require authorization covering the target and effects; reuse an existing approval when it already covers them.

## One cycle

1. **Observe:** Read current evidence and select the highest-value unresolved question.
2. **Baseline:** Reproduce the bug or capture the named metric under declared conditions. If reproduction is impossible, write a falsifiable failure contract rather than claiming a cause.
3. **Hypothesize:** State one candidate root cause, predicted evidence, and what would falsify it.
4. **Probe:** Run the smallest safe read-only check that distinguishes the hypothesis from alternatives.
5. **Classify:** Record the command or method, result, evidence location, confidence change, limitations, and provenance. Deterministic output remains separate from agent interpretation.
6. **Decide:** Finish as `READY_FOR_PLAN`, run one new targeted cycle, ask the human a bundled material question, or stop with `BLOCKED`, `BUDGET_EXHAUSTED`, or `NO_PROGRESS`.

These are discovery outcomes, not `STATE.json` states: `READY_FOR_PLAN` moves the run to `PLAN`; a needed human answer to `WAITING_DECISION`; `BLOCKED`, `NO_PROGRESS`, or `BUDGET_EXHAUSTED` to `BLOCKED`, or to `WAITING_DECISION` when a human decision can unblock it.

Two consecutive cycles that add no material evidence are `NO_PROGRESS`; stop that investigation loop, reconsider the hypothesis, or ask for missing context. Do not repeat an unchanged command without a changed hypothesis. Never weaken a test, scanner, budget, SLO, or invariant to produce a ready state.

## Plan-ready packet

Planning may begin when the packet contains:

- scope and non-goals;
- verified baseline or reproducible failure contract;
- affected paths, dependencies, and owner;
- confirmed facts, unresolved assumptions, and confidence;
- acceptance criteria and exact verification methods;
- applicable security, compatibility, performance, scale, recovery, and rollout constraints;
- human decisions still required.

For performance and scale, the packet must distinguish measured values, model estimates, human-approved SLOs, and unknowns. A registered-user target, static scan, or capacity equation alone is not proof of production readiness.

## Handoff and re-entry

The Planner consumes the packet; implementation agents receive only approved contracts and relevant evidence. If implementation or QA disproves the discovery hypothesis, return to one bounded discovery cycle with the new evidence. Do not restart broad discovery or erase the failed hypothesis.

Bug close-out: [behavioral-testing.md](behavioral-testing.md#close-the-bug-before-starting-follow-up-work).
