# Spec to verifiable slices

Use this example when a feature needs a compact requirement baseline and behavior-oriented work breakdown. It does not create remote tickets or run the slices.

```text
Harness standard: add CSV export for the existing order search results.
Respect the current project/account authorization and filter behavior.
Use the repo's existing export service and test interfaces.
Turn the accepted decisions into a compact spec and verifiable slices.
Keep the work local; remote tracker work is not requested.
```

Before drafting, inspect current search filters, account isolation, export format and tests. If product documents do not settle whether export covers all matches or only the visible page, ask that material question with a recommendation. The available file locations and commands are facts for the agent to find.

Once scope is settled, record the baseline in the existing spec convention or the active `WORKFLOW.md`: intended exported records, filtering, access rules, columns/escaping, size limits and observable acceptance. The illustrative decisions below are assumed for this example only: the user selected all matches up to the approved cap and a fixed column contract.

| Slice | Delivered behavior and verification | Blocks on |
| --- | --- | --- |
| A | Export a bounded filtered result set through the existing account-scoped service; reading the exported file shows the accepted columns, escaping and rows, and another account cannot export them | Accepted result/column/limit contract |
| B | Download those bytes through the existing application endpoint and UI action; integration/interaction evidence checks the same filters, permissions and error state | A's verified service result and contract |
| C | Complete the empty/over-limit/cancellation cases at the same boundaries and verify the complete user flow at the integration tip | B's request/interaction contract |

This example is mostly sequential. It needs no parallel workers or extra task graph. If a slice turns into independent work with stable artifact inputs, apply the existing graph/isolation contract rather than copying an upstream automatic fan-out rule.

For requested TDD, start A with one failing behavior check through the existing interface and a literal expected export fixture. Make it pass before adding another case. Do not assert a private serializer's call order or generate all UI tests against a guessed endpoint first.

Review the integration result against the baseline and applicable conventions. Keep missing acceptance separate from a maintainability suggestion. If a PR is requested, its body can show the export flow, before/after evidence and the effects a rollback cannot undo, such as an already-downloaded file. Do not open or publish anything solely because this example names a PR.

For a separately requested retro, a repeated quoting mistake might justify an export fixture or a wired existing check; difficulty finding the export entry point might justify one navigation pointer. Propose those changes from the observed session instead of silently adding global instructions.
