# Graph Engineering feature example

Use this when a feature has genuinely independent work after one contract is stable. The companion [machine-readable graph](graph-engineering-feature.json) is intentionally explicit: a centralized Project Manager owns routing and merge, Frontend and Backend have disjoint write scopes, QA can request at most two repair rounds, and publication cannot run without human approval.

```text
Harness standard with Graph Engineering:

Add saved filters to the existing product. Keep the current authentication and design system. Inspect the repository first, stabilize the API and UX-state contract, then compile a task graph.

Parallelize only work that does not consume the other worker's output. Give every node an owner, input/output artifacts, repo-relative read/write scope, deterministic success criteria, time/attempt bounds, and a stop condition. Use one Project Manager to merge. QA must run the acceptance matrix in a separate pass and may request at most two repair rounds. Ask me before any schema choice, paid service, deploy, publish, or other expensive-to-undo action.

Success means authorized users can create, rename, apply, and delete their own filters; negative authorization, empty/loading/error states, keyboard access, responsive behavior, regression tests, and the agreed performance budget all have evidence.
```

Validate before execution:

```bash
npx github:kingggg5/harness graph-validate --graph examples/graph-engineering-feature.json
```

Why this shape:

- `plan → frontend/backend → merge` is a centralized diamond because the two implementations are independent only after the contract is approved.
- `qa → repair → qa` is a bounded evaluator loop, not an open-ended retry.
- `acceptance → publish` is a human gate immediately before a consequential effect.
- A strictly sequential migration, a one-file fix, or a tool-heavy task that needs one continuous reasoning chain should stay with one owner instead of copying this graph.
