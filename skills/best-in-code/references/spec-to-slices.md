# From intent to verifiable slices

Load this for an explicit spec, ticket breakdown, design interview, or a feature too broad to implement from the current acceptance criteria. Small implementation-ready changes use the normal quick route. The goal is a testable baseline and a bounded implementation plan with real dependencies.

## Resolve decisions from evidence

Start with the request, existing behavior, relevant tests and maintained project documents. Look up discoverable facts before asking the human. Read an existing `GLOSSARY.md` and applicable ADRs when terminology or a prior decision affects the change. A project glossary describes domain language; it does not replace Harness canonical memory or authorize tools.

For a material open choice, state what it changes and the recommended option with its tradeoff. Ask a small batch of questions whose prerequisites are already settled; defer dependent questions until their prerequisites are answered. Continue work independent of the answer. Stop questioning when acceptance and implementation can proceed within the authorized scope, not when every imaginable design branch has been explored.

If the user asks to synthesize an existing discussion into a spec, use the decisions already made. Label remaining material questions explicitly; do not restart an interview or quietly choose missing business rules. A prototype is useful only to answer one unresolved design question. Bound its scope, keep the decision-rich result and source pointer, and do not turn a throwaway experiment into production scope.

## Keep one requirement baseline

Follow the repository's spec convention. Otherwise use the requirement baseline and acceptance table in the current `WORKFLOW.md`; a planning-only request can return the same content in the response without initializing a delivery run. Record:

- user-visible problem, intended outcome, actors and in/out scope;
- settled behavior, known facts, assumptions and unresolved decisions;
- interface/data compatibility and applicable architecture decisions;
- observable acceptance criteria and the public boundaries that verify them;
- dependencies, rollback/rollout needs and genuinely missing authority.

Size the detail to the feature. Include user stories or state transitions when they clarify distinct behavior. Keep stable domain/interface decisions in the baseline and concrete file locations in implementation packets, where they can be checked against the current tree. Preserve a prototype type/schema snippet only if it expresses a decision more precisely than prose.

Writing a spec does not require a tracker account. Prefer local project artifacts unless tracker use was requested or already authorized. Before creating or updating remote issues, verify the configured repository/project and the user's authorization. Never infer a `gh` backend, new tracker setup, parent-issue closure or skill installation from a planning recipe.

## Plan slices by delivered behavior

Use the `WORKFLOW.md` task table for ordinary work. Use the existing [task graph contract](graph-engineering.md) only when its activation rules apply. Each slice should carry one behavior through the affected layers and its verification, so it can demonstrate an outcome. Do not force UI, database or API work into a slice when that layer is unrelated.

A compact slice packet has an objective, requirement IDs, dependencies and consumed artifacts, ownership, observable acceptance, verification, and limits. A blocker exists only when it supplies a required artifact, interface or decision. A slice is ready only when those blockers are complete and their evidence remains valid. Planned slices with no raw ambiguity do not need another requirements or triage pass.

For a broad rename or schema/type migration that cannot land as independent features, use expand/migrate/contract: introduce a compatible form, move callers in bounded batches, then remove the old form after all callers and stored-data compatibility are checked. If intermediate batches cannot stay valid, name an integration-only verification boundary and keep them on an explicitly selected integration branch; never imply each batch is independently releasable.

## Integrate a whole spec when requested

A spec implementation request authorizes the implementation, not unrestricted parallelism or publication. Follow [execution isolation](execution-isolation.md) and the approved agent/model plan. Sequential work remains with one owner when no authorized isolated worker capability exists.

For an authorized parallel graph, schedule only the ready frontier. Workers receive bounded pointers to the spec, slice, evidence and verified base revision, with disjoint write scopes. Confirm each worktree's base before mutation. If it is wrong or dirty, preserve its contents and resolve the mismatch; do not reset it merely to follow a template.

One integration owner accepts commits, checks ancestry and interface compatibility, runs relevant verification, and advances dependent slices. A conflict or failed check keeps the affected slice unfinished. Mark tickets resolved only after the same acceptance evidence is available at the integration tip. Open or update a PR only within the user's authorization or the established delivery contract, when the branch actually has changes to review.
