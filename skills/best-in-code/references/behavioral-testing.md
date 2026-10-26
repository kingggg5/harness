# Behavioral tests and test-first work

Documentation, reversible formatting and trivial edits usually need inspection and existing checks, not new tests.

## Choose an observable boundary

Use the highest practical boundary that exercises the real behavior: an exported function, CLI operation, request handler, or user interaction. Prefer an existing test seam. State what callers should observe and how the proposed check could fail if that behavior breaks. Resolve a new seam with the user only when it changes a material interface or requirement; an existing approved public interface supplies the ordinary test contract.

Expected values come from the spec, a worked example, a known-good fixture or independently established evidence. Do not reproduce the implementation's algorithm in an assertion. A test named after an internal call count or private helper is usually coupled to structure; keep such observations only when they prove a real contract, such as no paid request on denied input or no process launch without authorization.

Use real domain collaborators where feasible. Fake only boundaries that would need credentials, charges or external effects; do not mock internal layers until the test stops exercising the behavior. Inspect storage or side effects when that state is the contract under test, as with persisted-data, concurrency or security invariants.

## Work one behavior at a time

For requested TDD, repeat a small cycle: add one test for the next observable behavior and confirm it fails for the expected reason, not a missing dependency, invalid fixture or unrelated failure; make the smallest coherent change that passes it; refactor only within the green slice and authorized scope.

Avoid generating a speculative suite for an interface that has not been decided. Do not invent features to satisfy guessed tests. If code is already fixed before test-first work begins, say so; record the observed regression coverage rather than claiming an unobserved red-to-green result.

## Make the reproduction discriminating

For a difficult bug, choose a feedback loop that reaches the user's exact symptom: a focused failing test, fixture-driven CLI, controlled request, browser flow, isolated trace replay or differential comparison. Pin time, randomness, input and environment. Minimize the case while keeping the failure and enough context to recheck the original scenario.

Sanitize command lines, headers, outputs and captured artifacts before showing or retaining them. Use credentials through environment or approved secure storage; quote only signal-bearing lines. A reproduction against production, load/fuzz experiment or paid API needs authorization for that actual target and effects.

If the environment cannot reproduce the failure, continue safe evidence inspection, separate candidate causes from findings, and report what remains unverified. Do not require a perfect reproduction as a reason to abandon accessible diagnosis, and do not claim a causal fix without evidence.

After the fix, rerun the focused regression and the original scenario where available. Remove tagged temporary diagnostics you introduced and preserve relevant sanitized evidence. Use [discovery-loop.md](discovery-loop.md) for investigation budgets and hypothesis changes.

## Close the bug before starting follow-up work

Complete the original behavior change and its available verification before proposing a new phase. The handoff names the symptom, cause supported by evidence, changed behavior, checks actually run and residual uncertainty. Keep these two claims separate:

- **Repair evidence:** the original scenario or another representative check demonstrates the intended behavior.
- **Regression coverage:** a retained test exercises the actual caller chain that triggered the bug.

When the repair is verified but no suitable test seam exists, state the coverage gap; do not claim an unrelated unit test protects it. Explain the smallest missing interface or observable boundary and propose that architecture work as a separate scope decision. A missing seam alone does not undo demonstrated repair or authorize a broad refactor.

Required acceptance and verifier checks still govern completion. If the approved contract requires retained regression coverage, that requirement remains incomplete until a representative test or an explicitly accepted alternative exists; never waive it to report a passing delivery.

If verification cannot establish the intended behavior, report the fix as unverified and continue safe diagnosis within the task's limits; a retrospective never substitutes for completing the bug. Report the original fix first. When evidence points to a repeated mechanical mistake, an omitted existing check, navigation friction or unnecessary context/tool work, the handoff may propose the smallest prevention step. That recommendation never runs an unrequested retrospective, inspects unrelated sessions, rewrites steering files, invokes an unavailable/user-only skill, creates an external issue, installs a tool or spawns a new task; an explicitly requested retro uses [review-and-retrospective.md](review-and-retrospective.md). Follow-up implementation needs authorization covering its own changes; reuse existing authorization when it already includes them.
