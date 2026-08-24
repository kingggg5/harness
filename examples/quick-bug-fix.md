# Quick bug fix

Use this when the failure is reproduced and the change should stay narrow.

## Prompt

```text
Harness quick: Fix the reproduced off-by-one error in src/pagination.ts. Keep the public API and response shape unchanged. Run the existing pagination tests and add one regression case for the final page. Stop and ask if the current behavior is ambiguous.
```

## Expected route

- Harness keeps discovery and planning short.
- One implementation pass owns the bounded file set.
- QA is a separate labeled pass unless an independent context is available.
- The handoff includes the failing case, changed files, exact test command, and result.

Use `quick` only because the evidence and boundary are already known—not because verification matters less.
