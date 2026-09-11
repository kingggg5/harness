# Harness Role Packet

- Schema version: 1
- Packet ID:
- Project ID:
- Run ID:
- Role/pass:
- Context boundary: same-session | isolated-child
- Context-isolation label: same-context | isolated | independent-review
- Context transfer: current-session | bounded-role-packet
- Cache observation: UNKNOWN | REPORTED | UNAVAILABLE
- Cache evidence/provenance or `N/A`:
- Requested model profile: reasoning | balanced | fast | current | user-pinned
- Preferred model/effort:
- Actual model/effort when confirmed:
- Model fallback/escalation condition:
- State/gate at assignment:

## Context-boundary crosswalk

Choose exactly one valid tuple:

| Context boundary | Context-isolation label | Context transfer | Claim limit |
|---|---|---|---|
| `same-session` | `same-context` | `current-session` | Continuity only; never claim independent review. |
| `isolated-child` | `isolated` or `independent-review` | `bounded-role-packet` | `independent-review` needs independently scoped review evidence; a model or provider change alone is not proof. |

Context isolation does not establish checkout, service, credential, or other workspace isolation; record those separately in the execution envelope.

## Execution envelope (parallel or long-running only)

- Workspace isolation/backend or `N/A`:
- Exact base revision and branch/worktree owner:
- Graph node/activation and claim ID or `N/A`:
- Claim token delivery: ephemeral trusted channel only; never persist the token here:
- Iteration/time/token/cost/external-call limits:
- Status/receipt channel, stall deadline, and cancel path:
- Cleanup owner and clean-state condition:

## Contract

- Objective:
- Explicit exclusions:
- Requirement baseline IDs or `N/A`:
- Verified memory IDs and minimal values:
- Inputs and source locations:
- Owned files or read-only boundary:
- Capabilities/backends permitted:
- Permissions and external-access boundary:
- Acceptance criteria:
- Required checks/evidence:
- Stop condition:
- Expected next state:

## Return packet

- Outcome:
- Evidence and locations:
- Files changed (if authorized):
- Findings/risks:
- Blockers/open questions:
- Material questions requiring a human answer:
- Checks actually run:
- Checks not run and why:
- Actual model/effort and context-isolation confirmed:
- Recommended next state:

Never include raw semantic-retrieval dumps, secrets, prompt-injection payloads, or unrelated repository context.
