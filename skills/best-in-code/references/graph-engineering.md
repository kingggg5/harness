# Graph Engineering

Graph Engineering shapes how work moves between bounded jobs. It is a conditional Planner/Architect pass, not an eighth permanent role, another provider, or permission to spawn agents. The Project Manager remains the central coordinator and sole owner of shared Harness state.

## Two graph levels

- The lifecycle graph in [workflow-graph.md](workflow-graph.md) is the one canonical macro graph. `STATE.json` remains its machine-readable authority.
- `.harness/TASK-GRAPH.json` is an optional run-scoped execution contract compiled from `assets/templates/TASK-GRAPH.json`. It describes jobs, real dependencies, artifacts, ownership, limits, and gates for one complex run. It never replaces `STATE.json`, `WORKFLOW.md`, or human approval.

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

For a complex run that must survive process/session loss, use the optional Project Manager-owned [graph runtime ledger](graph-runtime.md). It adds atomic claim/finish receipts, graph and artifact digests, Git ancestry and write-scope verification, bounded loop activations, timeout reporting, and fail-closed resume. It remains a ledger, not an autonomous executor.

At run completion, remove the graph from active annexes and archive it with the workflow only when its plan/evidence is useful. Do not load an old task graph as current intent.

## Context packets and execution

For a whole-spec implementation, read [spec-to-slices.md](spec-to-slices.md): only slices with completed, verified prerequisites are ready. Keep acceptance at the integration tip and preserve the existing capability, workspace and model authorization.

The Project Manager emits one minimal role packet per scheduled node: objective, verified memory/source IDs, exact input artifact names, exclusions, read/write scope, capabilities, checks, and stop condition. Pass artifacts, not whole conversations. Re-verify stale project-map, web, retrieved-memory, or previous-node claims before they can drive code or a gate.

Parallel execution requires verified isolated-worker capability, disjoint ownership, one exact base revision, and the workspace/shared-resource contract in [execution-isolation.md](execution-isolation.md). A task graph with `max_parallel > 1` must select `provider-isolated` or `git-worktree`; otherwise preserve the same graph as labeled sequential passes. Worktrees do not isolate ports, databases, caches, credentials, processes, or external services. A different model does not make a verifier independent. A model may perform work inside a node; it must not silently rewrite routing, add nodes, extend limits, authorize side effects, or write the shared runtime ledger.

When independent slices justify a graph but child/parallel agents are unauthorized, keep the real dependencies and select `max_parallel: 1` with `isolation_strategy: "same-worktree-sequential"`. One owner executes the ready nodes sequentially; the graph does not grant agent permissions. A simple sequential feature still needs only the `WORKFLOW.md` task table under the activation rules above.

## Knowledge graph boundary

Do not turn every project into a knowledge graph. Harness already separates authoritative atomic memory (`MEMORY.json`), generated readable views (`CONTEXT.md`), current run state (`WORKFLOW.md`/`STATE.json`), and optional source-grounded topology (`PROJECT-MAP.md`). That is sufficient for ordinary software delivery and remains portable across models.

Consider a separate knowledge-graph product lane only when named competency questions repeatedly require multi-hop relationships, temporal validity, entity resolution, and provenance that flat records cannot answer well. Begin with the questions and ontology, keep immutable source material as truth, attach time and provenance to relations, validate extraction/fusion deterministically, and let a human curate sources and schema. Any LLM-written wiki or graph is a derived compiled layer, never authority. Add storage or GraphRAG only after measured retrieval failures justify the operational cost.

## Research basis

The dated evidence behind this design (checked August 2026) lives in [research-basis-2026.md](research-basis-2026.md#graph-engineering); read it only when changing this policy.

## Runtime selection

| Runtime | Choose when | Required proof before adoption |
|---|---|---|
| Harness JSON contract + provider passes | Default; portability, auditability, or graph execution does not need to survive a process restart | Validator pass, truthful capability mapping, and recorded node evidence |
| Bundled local graph ledger | An approved Git-backed run must survive provider/process restarts or reconcile concurrent worker receipts | Exact baseline, active Project/Run binding, atomic ledger tests, content-addressed artifacts, commit ancestry/scope checks, and Project Manager-only writes |
| Custom deterministic scheduler | Product already has a trusted queue/state engine and only model nodes are nondeterministic | Atomic state transitions, leases/timeouts, idempotency, bounded retries, receipts, recovery and observability tests |
| LangGraph adapter | A Python/JavaScript service genuinely needs persisted checkpoints, pause/resume, replay, and human interrupts | Current official API check, durable checkpointer, stable thread identity, serializable state, migrations, and side-effect replay tests |

Current [LangGraph documentation](https://docs.langchain.com/oss/python/langgraph/overview) describes durable execution and human-in-the-loop as checkpointer-backed features. Resume needs the same thread configuration; replay skips completed upstream nodes but re-executes downstream nodes, including API calls. Therefore consequential actions still require Harness approval binding and idempotency instead of trusting replay semantics.

Frameworks such as Google ADK, AutoGen, or another scheduler may execute the same contract only after current official documentation, maturity, persistence, recovery, security, and human-interrupt semantics are verified for the target project. None is a Harness dependency by default.
