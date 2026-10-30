# Graph Engineering

Graph Engineering shapes how work moves between bounded jobs. It is a conditional Planner/Architect pass, not an eighth permanent role, another provider, or permission to spawn agents. The Project Manager remains the central coordinator and sole owner of shared Harness state.

## Two graph levels

- The lifecycle graph in [workflow-graph.md](workflow-graph.md) is the one canonical macro graph. `STATE.json` remains its machine-readable authority.
- `.harness/TASK-GRAPH.json` is an optional run-scoped execution contract compiled from `.harness/runtime/assets/templates/TASK-GRAPH.json`. It describes jobs, real dependencies, artifacts, ownership, limits, and gates for one complex run. It never replaces `STATE.json`, `WORKFLOW.md`, or human approval.

Activate the task graph when the human explicitly requests graph execution, or when a standard/full run has a real fan-out/fan-in, a multi-module or multi-service boundary, an evaluator loop with a measurable rubric, or a consequential action that benefits from an explicit gate. Skip it for quick work, a strictly sequential reasoning chain, or work whose coordination/tool overhead is likely larger than its independent shards.

## Select the smallest useful shape

| Work shape | Use | Avoid |
|---|---|---|
| One bounded or sequential chain | One owner with labeled passes | Agent fan-out that fragments required context |
| Independent jobs after a stable contract | Centralized diamond: plan, parallel disjoint workers, one merge owner, QA | Independent agents merging their own unchecked conclusions |
| Mutually exclusive path | Deterministic router and one selected lane | Running every lane merely because it exists |
| Clear measurable defect/rubric | Bounded evaluator → repair → evaluator loop | Open-ended self-reflection or “until good” |
| Expensive-to-undo effect | Human node immediately before the effect | Approval on every harmless step or no approval at all |

Use this stop rule before every fan-out:

1. Name the artifact each child needs and produces.
2. Delete an edge when the target does not consume the source output. That is a fake dependency.
3. Keep sequential work with one owner when each step needs the full previous reasoning state.
4. Use one coordinator to route, contain errors, own integration, and update Harness state.
5. Cap parallelism, attempts, transitions, tool use, time, and loop rounds before execution.

## Compile the run contract

Copy the task-graph template without overwriting an existing graph, populate the current Project ID and Run ID, list it under `INDEX.md` active optional annexes, then validate it:

```text
npx github:kingggg5/harness graph-validate --graph .harness/TASK-GRAPH.json
```

Each node must declare one meaningful owner, objective, required/optional artifact inputs, unique outputs, repository-relative read/write scopes, attempts, timeout, side-effect class, and observable success criteria. Every data or loop edge must name an artifact produced by its source and consumed by its target. A fan-in declares `join`; a merge node's write scope contains the input owners' scopes it integrates; a loop declares `max_rounds`; a consequential node has an incoming human `on_approve` control edge, one attempt, and an idempotency key bound to the run and exact approved artifact.

The validator rejects unknown fields, ambiguous/escaping scopes, non-loop cycles, unbounded loops, fake data edges, unreachable nodes, conflicting unordered write scopes, and consequential effects without a human gate. Passing validates structure only; it does not prove a prompt, implementation, model, tool, or result is safe or correct.

## Runtime selection

By default, run the validated contract as provider passes with a truthful capability mapping and recorded node evidence. A run that must survive process or session loss can add the Project Manager-owned [graph runtime ledger](graph-runtime.md).

An external scheduler (a custom queue, LangGraph, Google ADK, AutoGen or similar) is never a default dependency. Adopt one only after verifying its current persistence, recovery and human-interrupt semantics for the target project. Replay can re-run downstream effects, so consequential nodes keep Harness approval binding and an idempotency key.

At run completion, remove the graph from active annexes and archive it with the workflow only when its plan/evidence is useful. Do not load an old task graph as current intent.

## Context packets and execution

For a whole-spec implementation, read [spec-to-slices.md](spec-to-slices.md): only slices with completed, verified prerequisites are ready. Keep acceptance at the integration tip and preserve the existing capability, workspace and model authorization.

The Project Manager emits one minimal role packet per scheduled node: objective, verified memory/source IDs, exact input artifact names, exclusions, read/write scope, capabilities, checks, and stop condition. Pass artifacts, not whole conversations. Re-verify stale project-map, web, retrieved-memory, or previous-node claims before they can drive code or a gate.

Parallel execution requires verified isolated-worker capability, disjoint ownership, one exact base revision, and the workspace/shared-resource contract in [execution-isolation.md](execution-isolation.md); `max_parallel > 1` must select `provider-isolated` or `git-worktree`. Without that capability or authorization for child/parallel agents, keep the real dependencies and set `max_parallel: 1` with `isolation_strategy: "same-worktree-sequential"`: one owner runs the ready nodes as labeled sequential passes. The graph never grants agent permissions. A model may perform work inside a node; it must not silently rewrite routing, add nodes, extend limits, authorize side effects, or write the shared runtime ledger. A simple sequential feature needs only the "Task graph" table in `WORKFLOW.md`.

## Knowledge graph boundary

Do not turn projects into knowledge graphs: `MEMORY.json`, generated views, `WORKFLOW.md`/`STATE.json` and `PROJECT-MAP.md` already separate authority. Any LLM-written wiki or graph is a derived layer, never authority.

## Research basis

The dated evidence behind this design (checked August 2026) lives in [research-basis-2026.md](research-basis-2026.md#graph-engineering); read it only when changing this policy.
