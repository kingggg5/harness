# Practitioner Methods

Read this when choosing how to work in a field that has no dedicated Harness reference: crash or bug triage, security, data migration, API or contract change, incidents, or a product/business question. It replaces persona framing ("act as a senior engineer") with the concrete methods, tools and evidence that people who do that work rely on.

## Method, not persona

A persona label adds no capability; a named method changes what gets done and what evidence comes back.

1. Name the field and the practitioner's first moves for this task (rows below). Use only the rows and moves the task needs.
2. For the moves you will use, find the project's own instrument: scripts in the manifest or Makefile, CI jobs, configured linters and scanners, test helpers and fixtures, and the data sources catalogued in `.harness/SOURCES.json` ([evidence-sources.md](evidence-sources.md)). The project's tool outranks a generic one.
3. Run the method and keep its output as evidence. When a tool is missing, use the next-best method and say so in the report. Never install a tool, connect an account, or reach or change production without authorization for that action.
4. When current practice is uncertain (a library's migration path, a vendor's recommended check, a standard's current version), look it up through [research-routing.md](research-routing.md) instead of answering from memory.

Role passes and packets carry the same content: the methods, tools and evidence the pass needs, never "you are an expert X".

## Fields with their own reference

These already define the practitioner's method; follow them rather than a summary here.

- Bug: reproduce the exact symptom, shrink it to a failing test, read the whole stack trace, and bisect a regression (`git bisect run`, in a disposable worktree when the tree has uncommitted changes) → [behavioral-testing.md](behavioral-testing.md), [discovery-loop.md](discovery-loop.md).
- Performance → [performance-engineering.md](performance-engineering.md). UI → [frontend-skill-routing.md](frontend-skill-routing.md). Code review, including the diff target for uncommitted work → [review-and-retrospective.md](review-and-retrospective.md). Requirements → [requirements-analysis.md](requirements-analysis.md).

## Field methods

| Field | Practitioner's first moves | Typical instruments | Evidence it returns |
|---|---|---|---|
| Crash or bug triage | Group by signature, count affected users or sessions, check trend and first-seen release, map the top in-app frame to code, cross-check support tickets | crash reporter or error tracker, release tags, ticket search | ranked groups with counts and code locations ([evidence-sources.md](evidence-sources.md)) |
| Security | Map trust boundaries, follow untrusted input to each sink, check authentication and authorization on every path, run the project's scanners | SAST such as Semgrep or CodeQL, dependency audit (`npm audit`, `pip-audit`), secret scanning | exploit scenario or proof of the guard, scanner output |
| Data migration | Expand/contract, backfill in bounded batches, dry run on a copy, compare counts and checksums, rehearse rollback | migration tool, staging copy, SQL counts | before/after counts, timing, rollback result |
| API or contract change | Find every caller, decide compatibility, add contract tests, plan deprecation | reference search or LSP, contract or snapshot tests | caller list, old and new contract tests passing |
| Incident | Propose the mitigation (rollback, flag off) for approval, build a timeline, measure the blast radius, then find the cause | dashboards, logs, deploy and flag history | timeline, affected scope, cause with evidence |
| Product or business question | Query the real usage or business data, segment it (plan, platform, cohort, funnel step), read the code path that produces it, sample the related customer issues | analytics or BI queries, event schema, ticket search | numbers with query and period, code and ticket references |

A row is a starting method, not a checklist to complete: stop when the evidence answers the question, and add a method only when the evidence so far leaves a material doubt.
