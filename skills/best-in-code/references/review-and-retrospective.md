# Review, PR evidence and session retrospectives

Load the relevant section for a diff/PR review, writing a PR description, or an explicit session retrospective. These are separate tasks: a review remains read-only; writing a description does not authorize publishing; a retro does not silently become environment or product changes.

## Review against requirements and conventions

Pin the review target from the user's request: commit/branch/tag, merge base, staged changes or working-tree diff. Resolve explicit refs and inspect the actual diff before drawing conclusions. A branch review commonly uses its merge base; a staged/unstaged review must include the selected changes instead of only `HEAD`. If the target is empty, report that. Ask about the target only when several plausible choices materially change the scope.

Find the requirement/spec in the request, provided issue, maintained project docs or current workflow baseline. Read applicable coding conventions and enforced checks. An absent spec is a gap in evidence, not permission to invent acceptance criteria.

Evaluate two lenses and label evidence for each:

- **Requirements:** missing/partial behavior, contradictions, unsupported scope additions, error paths, compatibility and acceptance coverage.
- **Conventions:** confirmed repository rule violations and maintainability risks in the changed code. A heuristic smell is a candidate until a concrete impact is demonstrated. Do not restate issues already rejected by a tool or prescribe unrelated cleanup.

For each actionable finding, give the scenario, affected path/line, expected rule/behavior, consequence and smallest fix. Keep deterministic results distinct from reviewer interpretation. A changed model alone does not provide independent review. With authorized isolated readers, supply the same pinned diff and relevant sources in separate scoped packets; otherwise use accurately labeled same-agent passes. Aggregate by root cause without hiding whether the problem is requirement or convention driven.

The implementation agent remains responsible for repository rules during the build. Review provides a second check; it does not excuse knowingly violating conventions. Use [engineering-standards.md](engineering-standards.md) for the existing risk and lens policy.

## Make a PR assessable

Respect the repository PR template. Lead with the concrete trigger/problem and resulting behavior, then the evidence actually collected. For a simple change, one or two sentences and verification are enough. Add a small diff sketch, call/file tree or diagram only when it explains a boundary or flow better than prose. Do not force a visual for a one-line edit.

Show before/after output, screenshots, or a regression result when available. Record unverified behavior and accepted limits. For material migrations or effects, state whether rollback can restore code and data, affected users/components, rollout controls and the approval still needed. A reversible code deploy can still send an irreversible external effect; assess the actual operation, not only the Git diff.

Do not claim that tests, independently scoped review or rollback were performed unless their evidence exists. Creating a PR, pushing, merging, closing tracker items and publishing require authorization for that action; formatting a proposed body supplies none of it.

## Retrospective: improve the next run

Run a retro when the user requests it or an approved run contract includes it. Default to the current session; use other logs only when the user identifies the session and access/scope are authorized. Read evidence of time lost, repeated corrections, missing inputs and tool usage, keeping secrets and unrelated conversations out of the report.

A completed bug may expose a prevention opportunity or a missing test seam. Use [the bug close-out rule](behavioral-testing.md#close-the-bug-before-starting-follow-up-work) to report it without automatically starting a retrospective or architecture pass. If the retro is requested, ask what in the environment would have prevented the observed mistake; trace that answer to existing checks and navigation before proposing changes.

Return a short evidence-to-change mapping:

| Observed friction | Check first | Useful improvement |
| --- | --- | --- |
| Files or relationships repeatedly hard to find | Existing navigation/docs and source references | A focused pointer under the condition that needs it |
| A mechanical error escaped | Current lint/typecheck/test command and its CI wiring | Repair the existing deterministic gate, or add a scoped one when authorized |
| A judgment keeps needing correction | Existing standards and actual examples | One precise convention with its applicability and rationale |
| Agent input is large or duplicated | Current descriptions, references and measured tool output | Remove stale/repeated guidance; bound the relevant retrieval |
| Needed evidence was unavailable | Existing logs/read scopes and responsible owner | A proposed scoped evidence path, without new permissions assumed |

Inspect existing checks before proposing a new tool. A rule that can be enforced mechanically belongs in an appropriate check; instructions explain decisions the tool cannot make. Treat lacking automation as a proposal proportional to the project, not an automatic security finding or mandatory install.

Rank a few supported improvements by impact and effort. A diagnosis alone does not authorize rewrites, hooks, global instructions, dependency installs or access expansion. If asked to apply a retro, make the agreed scoped changes and verify them. Reusable project decisions use [memory-loop.md](memory-loop.md); a retro report never directly edits `MEMORY.json` or generated `CONTEXT.md` rows.
