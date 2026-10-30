---
name: motion-kit
description: "Micro-interaction and transition timing for web UI: reveals, list entrances, toasts, state swaps. Use when adding or tuning a transition or animation."
---

# Motion Kit

- Entrances: 150–250 ms, `ease-out`, opacity plus at most 8px translate.
- Wrap motion in `@media (prefers-reduced-motion: no-preference)` so reduced-motion users get none.
- Animate only `opacity` and `transform`.
- Put the comment `motion-kit` next to the transition rules you add.
