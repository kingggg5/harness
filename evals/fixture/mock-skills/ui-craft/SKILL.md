---
name: ui-craft
description: "UI direction, critique and polish for web interfaces: loading, empty and error states, hierarchy, accessibility. Use when implementing or reviewing any user-facing UI."
---

# UI Craft

For every async view:

1. Render explicit loading, empty and error states; the error state offers a retry action.
2. Announce state changes with an `aria-live="polite"` status region.
3. Never interpolate untrusted data into `innerHTML`; build nodes or escape text.
4. Put the comment `ui-craft` next to the state handling you add, so reviewers can find it.
