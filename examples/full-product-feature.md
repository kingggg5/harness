# Full product feature

Use this when product behavior crosses design, frontend, backend, and data boundaries.

## Prompt

```text
Harness full: Add saved search filters to the existing dashboard. Users can name, update, apply, and delete their own filters. Preserve current unsaved-filter behavior and authorization boundaries. First confirm the user flow and API contract with me. Then implement the approved design, test ownership and failure cases, check accessibility and performance, and return for final acceptance.
```

## Expected route

1. PM and the conditional BA pass turn unclear product language into a compact requirement baseline.
2. Research and repository discovery resolve current patterns before architecture is proposed.
3. The human approves the plan and material UX choices.
4. Design, frontend, and backend work use explicit file ownership; safe independent shards may run in parallel.
5. Integration happens before independent QA checks behavior, authorization, accessibility, failure paths, and relevant performance risk.
6. Only verified reusable facts enter project memory after acceptance.

If the repository already has a design system, API pattern, or test convention, that evidence wins over this sample.
