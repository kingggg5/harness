# Jev architecture overview

Use [jev-runtime.md](jev-runtime.md) for the shipped Jev, query-time context, route-cost and command-gate behavior. Use [async-operation-runtime.md](async-operation-runtime.md) for the Unreal Agent patterns and the language/runtime decision.

Harness uses a hosted TypeSafe Jev API only when the operator explicitly enables the `jev-public` path. The default schema-v3 selector is local. Jev returns validated typed recommendations; the kernel keeps authority over permissions, model trust, budgets and execution.

Exa, Gemini, Cua, local Jev, arbitrary MCP services and `tools/jev-assistant.mjs` are not shipped integrations here. External cost results are attributed to their source and must not be presented as Harness benchmarks. For actual support boundaries and setup, follow the runtime guide instead of configuration labels or historical architecture examples.
