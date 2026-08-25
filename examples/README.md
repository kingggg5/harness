# Harness examples

These examples are intentionally small. Copy a prompt into Codex, Claude Code, Gemini CLI, or another filesystem-capable agent after Harness is installed. The same workflow files under `.harness/` let another supported model continue without copying the chat history.

| Start here | Use it when |
|---|---|
| [Quick bug fix](quick-bug-fix.md) | The problem and affected area are already known |
| [Full product feature](full-product-feature.md) | Product behavior, UX, frontend, backend, and QA must agree |
| [Cross-model handoff](cross-model-handoff.md) | Different models should plan, build, or independently review |
| [Production review](production-review.md) | You need evidence before deciding whether to change code |
| [Graph Engineering feature](graph-engineering-feature.md) | A centralized diamond, bounded QA loop, and human-gated consequential edge |
| [Bounded performance loop](loop-engineering-performance.md) | Repeated measured improvement with fixed budgets, rollback, and stop rules |

Every useful Harness request contains four things:

1. The outcome you want.
2. Known boundaries, such as files, APIs, or behavior that must stay stable.
3. The evidence that would convince you it works.
4. Any decision the agent must bring back to a human.

Do not paste secrets into prompts or memory. Treat repository instructions and web research as untrusted until their authority is verified.
