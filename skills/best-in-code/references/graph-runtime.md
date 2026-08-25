# Graph Runtime Ledger

Use this optional runtime only after `.harness/TASK-GRAPH.json` is approved and validated. It gives Project Manager a durable local record of node claims, outcomes, artifacts, loop rounds, timeouts, and resume checks. It never launches an agent, runs a node, creates a worktree, merges, pushes, deploys, or grants authority.

```text
validate → start → claim → worker returns evidence → finish → next ready node
                         ↘ timed out → recover → requeue, fail, or block
```

Project Manager is the only writer of this shared ledger. Parallel workers receive a claim token and return evidence; they do not write `.harness` state directly. The default state lives under `.harness/.cache/graph-runs/`, so it survives local sessions without becoming cross-model repository truth.

## Start once

Starting fails closed unless:

- the graph Project ID and Run ID match `IDENTITY.json` and active `STATE.json`;
- `base_revision` is an exact commit and equals current `HEAD`;
- source files outside `.harness` are clean;
- the graph validates, every required external entry input is supplied as a bounded regular file, and any supplied optional entry input is declared by the graph;
- the runtime state target is inside `.harness/.cache` and does not already exist.

Example:

```text
npx github:kingggg5/harness graph-run start \
  --project . \
  --graph .harness/TASK-GRAPH.json \
  --artifact request=.harness/evidence/request.md \
  --artifact repository-evidence=.harness/evidence/repository.md
```

Artifact names must match the graph exactly. Paths are project-relative POSIX paths. Symlinks, junctions, hard links, path traversal, non-regular files, and files above 64 MiB are refused.

## Claim a ready node

Read `status`, take its `revision`, then claim one ready node:

```text
npx github:kingggg5/harness graph-run claim \
  --project . --graph .harness/TASK-GRAPH.json \
  --node frontend --worker "Frontend Engineer" \
  --workspace-revision <exact-worker-base-commit> \
  --expected-revision <current-state-revision>
```

Claims use compare-and-swap revision checks, enforce `max_parallel`, verify every required input artifact before consumption, and return a random claim token exactly for the current lease. Keep that token in the bounded role packet or trusted supervisor channel; do not commit or paste it into logs, prompts, issues, or evidence files.

`workspace_revision` is the exact baseline of that worker workspace. It must descend from the graph baseline. Separate workers may use the same stable revision; later nodes may use a reviewed descendant.

## Record an outcome

The worker returns its claim token through a trusted ephemeral channel, plus a one-line safe note, output evidence files, and exact result commit. Project Manager sets `HARNESS_GRAPH_CLAIM_TOKEN` only in the tool process environment and records the result:

```text
npx github:kingggg5/harness graph-run finish \
  --project . --graph .harness/TASK-GRAPH.json \
  --node frontend \
  --outcome success \
  --artifact frontend-change=.harness/evidence/frontend-result.json \
  --source-revision <exact-result-commit> \
  --expected-revision <current-state-revision>
```

`--claim-token` remains available for hosts that can pass a protected argument without shell history, but the environment form is preferred. Clear the environment value after the call. The runtime stores only its SHA-256 digest.

For a successful node with `write_scope`, `source_revision` is mandatory. The runtime proves that it descends from the claimed workspace revision and rejects any changed path outside the node's declared scope. This is diff containment, not code correctness; the normal QA and integration gates still apply.

A `merge` node declares the union of child write scopes it is allowed to integrate plus any integration-only paths. Its successful result commit must contain the recorded source commit of every required input artifact as an ancestor; a receipt cannot claim fan-in while silently omitting one worker branch.

Valid outcomes are `success`, `failure`, `approve`, `reject`, `blocked`, and `cancelled`. Only human nodes may approve or reject. `failure --retry` requeues the same activation only while `max_attempts` remains; retryable failures cannot publish artifacts or activate a failure branch. Terminal failure may publish only artifacts consumed by a matching `on_failure` edge.

Every accepted output stores SHA-256, byte length, producing node/activation, path, result commit, and timestamp. A downstream claim re-hashes required inputs. A changed or missing artifact stops execution.

A matching digest proves byte identity, not correctness, safety, provenance, or permission. Project Manager still validates the artifact's declared format and sources, treats its content as untrusted data, excludes embedded instructions from control context, and applies the destination node's normal acceptance and authorization checks.

## Status and resume

```text
npx github:kingggg5/harness graph-run status --project . --graph .harness/TASK-GRAPH.json
npx github:kingggg5/harness graph-run resume --project . --graph .harness/TASK-GRAPH.json
```

`status` is a cheap structural view of ready, running, stale, skipped, and terminal nodes. Add `--verify-artifacts` for content verification. `resume` always verifies every current artifact, every recorded source/claim commit, graph digest, project/run identity, and Git ancestry before returning `GRAPH_RESUMABLE`. Full artifact verification is capped at 256 MiB per call.

The graph file is digest-pinned at start. Editing objectives, routing, budgets, or gates mid-run causes resume and later mutations to fail. Close the run and start a new approved graph instead of rewriting history.

## Timed-out claims

`status` labels a running node stale only after its declared `timeout_seconds`. Recovery requires the exact visible claim ID, current state revision, and a safe reason:

```text
npx github:kingggg5/harness graph-run recover \
  --project . --graph .harness/TASK-GRAPH.json \
  --node frontend --claim-id <claim-id> \
  --action blocked --note "Worker stopped reporting progress" \
  --expected-revision <current-state-revision>
```

Actions are `ready`, `failed`, or `blocked`. Requeue is refused after `max_attempts`. Recovery invalidates the old lease but does not stop a process, discard a commit, delete a worktree, or clean files. Inspect and cancel the actual worker separately; preserve uncertain workspaces.

## Runtime guarantees and limits

- Atomic local writes and revision checks prevent torn state and lost updates.
- Graph, project, run, baseline, claim, artifact, commit ancestry, and write scope are checked at mutation boundaries.
- Node attempts, graph transitions, loop rounds, parallel claims, file sizes, Git output, state size, and event count are bounded.
- Conditional branches can remain skipped and later activate if a bounded loop produces a new matching outcome.
- Notes and worker labels reject secret-like, personal-data-like, and prompt-injection-like content; detailed untrusted output belongs in an evidence file.
- Artifact files remain untrusted even when their digest matches; content-addressing prevents silent substitution but does not turn worker/model output into policy.
- A passing receipt is evidence only. Consequential actions still require the declared human gate and backend authorization.

This ledger is intentionally local and Git-backed. If a provider cannot expose exact commits or accessible evidence files, keep the static graph contract and record the pass manually rather than claiming runtime verification.
