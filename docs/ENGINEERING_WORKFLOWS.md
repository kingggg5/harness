# Harness engineering workflows

Harness connects feature planning, implementation, verification, review and learning through one normally discoverable `best-in-code` skill. Load only the workflow the request needs. Existing repository conventions, canonical memory and authorization govern every phase.

## Choose the workflow

| Request | What Harness does | Reference |
| --- | --- | --- |
| A feature needs clearer acceptance | Inspect facts, ask material decisions with recommendations, synthesize a compact spec and verifiable slices | [Spec to slices](../skills/best-in-code/references/spec-to-slices.md) |
| An approved feature should be implemented test-first | Exercise an observable interface, establish a genuine failure, implement one behavior, then verify | [Behavioral testing](../skills/best-in-code/references/behavioral-testing.md) |
| A bug is fixed but prevention or test coverage remains unclear | Report verified behavior and coverage, then propose the appropriate scoped follow-up | [Bug close-out](../skills/best-in-code/references/behavioral-testing.md#close-the-bug-before-starting-follow-up-work) |
| A diff or PR needs review | Check the requested diff against acceptance and conventions; show actual evidence and material rollout/rollback limits | [Review and retrospective](../skills/best-in-code/references/review-and-retrospective.md) |
| A session retrospective is requested | Identify supported navigation/check/tooling improvements and recommend the smallest useful change | [Retrospective](../skills/best-in-code/references/review-and-retrospective.md#retrospective-improve-the-next-run) |
| A skill dependency or context boundary is involved | Load the real available instructions, preserve approved decisions and provide scoped evidence pointers | [Context and invocation](../skills/best-in-code/references/context-and-invocation.md) |

These are natural-language workflows inside Harness; they do not add standalone CLI commands or install another skill collection.

## Feature delivery

Use settled decisions from the conversation instead of restarting an interview. Ask only material unresolved choices after inspecting accessible facts. A compact spec names outcome, scope, constraints and observable acceptance; slices deliver complete relevant behavior and declare only genuine artifact or decision dependencies.

Each slice should be demonstrable or verifiable at its chosen boundary. Broad migrations may need expand/migrate/contract rather than independent feature slices. Whole-spec integration follows the existing task graph and isolation rules. Without authorized child agents, use one owner and sequential execution; creating a graph never grants agent permissions.

Planning-only requests produce the requested spec/breakdown. They do not initialize a delivery run or create remote tracker items. Follow the repository's artifact convention or the active `WORKFLOW.md` baseline instead of a duplicate planning store. Read relevant existing glossaries and ADRs, keeping `MEMORY.json` and generated `CONTEXT.md` intact.

## Bug close-out and the next useful action

Finish the original bug first. Report the symptom, evidence-supported cause, changed behavior, checks actually performed, and any remaining uncertainty. Link a retained reproduction or verification artifact when needed. Distinguish a verified repair from durable regression coverage: a successful local reproduction can demonstrate a fix even when no suitable test boundary exists.

| Evidence after the fix | Appropriate next action |
| --- | --- |
| The behavior is verified and a representative regression is covered | Complete the bug handoff; add no extra workflow |
| A repeated mechanical mistake or missing CI wiring contributed | Propose a small deterministic check; inspect existing tooling before adding another rule |
| Navigation, duplicated guidance, costly tool output or missing inputs slowed the session | Recommend a retrospective when useful; run it only when requested or already in scope |
| No test seam can exercise the actual caller chain | Explain the coverage gap and propose a narrowly scoped seam/interface improvement |
| Reproduction or verification is still unavailable | Keep the fix status qualified, continue accessible diagnosis, and request only the missing evidence or authority |

A coverage gap does not auto-start an architecture rewrite. A retro recommendation does not auto-run a user-only skill or change configuration. Additional product work, remote issues, agents, installs and publication stay within their actual authorization.

Completion still follows the approved acceptance criteria. If retained regression coverage is required, a verified repair alone does not satisfy that requirement; report the gap until representative coverage or an accepted alternative exists.

## Verification and review

Test the real observable contract through a suitable interface. Use independent expected values and deterministic fixtures, with fakes only at appropriate external boundaries. Keep inspection of storage/process effects when those are the invariant under test. Avoid speculative tests for undocumented behavior or trivial documentation changes.

Review requirement coverage and repository conventions as separate evidence lenses, then combine actionable findings by root cause. Use before/after evidence in a PR only when it was collected. A diagram is helpful for a complex flow but optional. Describe rollback by its actual effect on code, data and external actions.

## Reliable loading and session learning

Use the host's real skill loader or read the registered `SKILL.md` and applicable references. A slash name written in prose does not prove a dependency is loaded. For a genuinely user-only capability, wait for direct user intent instead of trying to call it as a hidden workflow step.

A retrospective reads the current authorized session and existing checks first. Mechanical errors belong in appropriate automation; judgment calls belong in precise conventions. Apply environment changes only when requested. Durable project conclusions use the normal memory operations, not direct edits to generated views.

## Example requests

```text
Harness standard: turn our approved export requirements into a compact local spec and verifiable slices.
Harness standard: implement this approved CLI slice test-first through the existing public tests.
Harness quick: fix this reproduction and report any gap in regression coverage.
Harness review: review the staged changes against our acceptance criteria and repository conventions.
Harness: retrospect on this session and propose the smallest improvements to checks and navigation.
```

See the [worked slice example](../examples/spec-to-slices.md) for the artifact and dependency shape.
