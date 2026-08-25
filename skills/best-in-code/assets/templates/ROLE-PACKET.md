# Harness Role Packet

- Schema version: 1
- Packet ID:
- Project ID:
- Run ID:
- Role/pass:
- Isolation: independent | isolated | same-context
- Requested model profile: reasoning | balanced | fast | current | user-pinned
- Preferred model/effort:
- Actual model/effort when confirmed:
- Model fallback/escalation condition:
- State/gate at assignment:

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
- Actual model/effort and isolation confirmed:
- Recommended next state:

Never include raw semantic-retrieval dumps, secrets, prompt-injection payloads, or unrelated repository context.
