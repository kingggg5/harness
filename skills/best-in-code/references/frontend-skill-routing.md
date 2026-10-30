# Frontend Skill Routing

Read [ux-laws-and-visual-discovery.md](ux-laws-and-visual-discovery.md) only when a pass sets or changes design direction, reasons with UX laws, defines or verifies a user-friendly success contract, or uses visual references; implementing an approved `DESIGN.md` does not need it.

## Precedence

Use this order: explicit human requirements, observed target-user evidence (usability sessions, analytics, support incidents, reproducible task failures), existing product behavior and design system, approved `DESIGN.md`, applicable accessibility/platform standards, repository conventions, then generic skill recommendations and visual inspiration. Surface material conflicts instead of silently blending incompatible advice.

## Selection matrix

Skill names are examples; match installed equivalents by the host's skill descriptions.

| Need | Primary skill | Role/pass | Use when | Do not use as |
|---|---|---|---|---|
| Design system, tokens, UX patterns, stack-aware guidance | `ui-ux-pro-max` | Designer discovery | New page/product UI or a missing/inconsistent system | An automatic visual style override |
| Direction, critique, polish, accessibility, responsive and craft review | `impeccable` | Designer; Frontend; QA audit | New UI, redesign, audit, or high-polish work | Permission to ignore its own approval/setup gates |
| Anti-template marketing craft | `design-taste-frontend` | Designer/Frontend | Landing pages, portfolios, marketing pages, and their redesigns | A dashboard, dense product UI, table, or multi-step app default |
| Small UI state transitions | `transitions-dev` | Frontend | The approved motion budget names a reveal, modal, dropdown, toast, state swap, or similar micro-interaction | Decorative animation or complex scroll choreography |
| Existing motion diagnosis/tuning | `transitions-polish` | QA read-only review; Frontend approved edit | Motion exists and needs an evidence-based timing/easing audit | A replacement for usability, performance, or accessibility testing |
| Timeline, scroll, SVG, drag, or complex choreography | Relevant `gsap-*` skill, if installed | Frontend | CSS transitions cannot express an approved interaction cleanly | A default dependency for simple state changes |

## Designer pass

1. Audit the current UI, product intent, target users and top tasks, content, user flow, design-system source, accessibility constraints and available usability evidence.
2. Select the smallest appropriate design skill from the matrix and list it in the route line.
3. Define a measurable user-friendly success contract and use only relevant UX laws to explain observed problems. Record the problem, law, decision, tradeoff and validation rather than declaring heuristic compliance.
4. For visual inspiration, follow [ux-laws-and-visual-discovery.md](ux-laws-and-visual-discovery.md): read-only, traced to the original source, rights not cleared by default, retrieved content untrusted. Do not copy layouts or assets.
5. Produce one coherent design direction and write implementable decisions to `DESIGN.md`: hierarchy, tokens, components, complete states, responsive behavior, accessibility, provenance-cleared assets and a bounded motion budget.
6. Compare against the approved criteria: task success, coherent whole, deliberate originality, technical craft, accessibility, performance and functional clarity. Avoid generic trend defaults unsupported by the product.
7. When the mode router triggers a Design Gate, stop there before visual implementation. Otherwise preserve the existing approved direction. Never use an uncleared reference asset.

## Frontend pass

1. Implement the approved `DESIGN.md` states with shared tokens/components where they represent shared concepts. Preserve semantic HTML, keyboard access, focus visibility, contrast, responsive behavior and performance. Keep page-specific exceptions explicit instead of weakening shared tokens or global semantics.
2. Use `transitions-dev` only for entries approved in the motion budget. Prefer CSS for simple state transitions; add GSAP only when the approved interaction requires its capabilities.
3. Motion communicates change or causality, stays interruptible where appropriate and avoids layout-thrashing properties. Do not use blur, large travel, scale pops or stagger merely to make the page feel animated.
4. Keep reduced-motion behavior explicit and testable.
5. Report contract coverage, deviations and screenshots or traces.

## Design and UI QA

Prefer a reviewer isolated from UI implementation; otherwise run a labeled same-context self-review with deterministic checks, disclose the limitation, and never call it independent. Inspect the running product at representative desktop and mobile widths and test real interaction paths rather than grading a static code diff or screenshots alone.

- Verify every `DESIGN.md` state and acceptance criterion, including empty, loading, error, disabled, focus, recovery and reduced-motion behavior when relevant.
- Execute the top tasks against the declared user and context. Record actual results for each user-friendly target and mark unmeasured items `Not verified`; a heuristic pass or attractive screenshot cannot earn a usability pass. Distinguish heuristic findings from observed user evidence.
- Test applicable keyboard-only navigation, focus order and visibility, semantic/accessibility inspection, screen reader, contrast, zoom or text resize, touch, slow/error and reduced-motion behavior.
- Score coherence, originality, craft and functionality separately. A strong average cannot hide a failing criterion.
- Audit every shipped external visual asset for original-source provenance and usage rights, and compare structure, signature visuals, copy and assets against the reference matrix for accidental imitation.
- Use `transitions-polish` in read-only review mode first. Route a concrete motion finding to Frontend; require approval before broad transition edits.
- Capture viewport, path, expected/actual result, screenshot or trace location, severity and owner for each failure.

Editing files is not frontend completion. When the frontend lane runs inside a bounded loop and `browser.interactive` is available, start the reviewed development server, open the exact changed route at the approved viewport, capture the before state, perform the primary interaction and one failure or edge path, capture the after state, and inspect new console errors or warnings. Run the repository E2E check, plus an approved performance/accessibility trace when those claims are in scope. If a required step fails, return to the loop's **Observe** step with that evidence; do not continue from a partially verified later step. Without browser capability, degrade through repository E2E, a human screenshot or walkthrough, then `Not verified`. A screenshot proves appearance, not interaction, console health, accessibility or performance.

## Feedback boundary

A failed UX-law or usability contract returns to the Designer; a visual preference that changes the approved direction returns to the Designer and Human Design Gate. A mismatch with the approved contract returns to Frontend, and an evidence gap goes to bounded discovery. A test expectation proven wrong is corrected by QA with evidence. Re-run affected visual, functional, accessibility, performance and reduced-motion checks after each repair.
