# Provider Adapters

Harness keeps one canonical skill and plain `.harness/` state. Provider files only make that source discoverable; they do not copy the policy.

## Invocation mapping

| Environment | Invocation |
|---|---|
| Portable/natural language | `Harness: <task>` or `Harness full: <task>` |
| Codex skill | `$best-in-code <task>` |
| Claude Code plugin | `/harness:best-in-code <task>` |
| Gemini CLI | Ask it to use the `best-in-code` skill, or use the extension's discovered skill command |
| Generic filesystem agent | Tell it to read `AGENTS.md`, then `.harness/runtime/SKILL.md` on invocation |

Do not put provider aliases in canonical project memory.

Model names are adapter bindings too. Apply the provider-neutral profiles and context-boundary contract in [model-routing.md](model-routing.md); verify the actual launched model instead of inferring it from a requested alias. A provider without per-pass selection remains a truthful same-model fallback.

## Cache-aware routing telemetry

An adapter may expose cache telemetry only when its active provider/runtime reports attributable counters for that exact pass. Schema-v1 contracts send protocol v1, which permits only the legacy usage receipt; schema-v2 contracts send protocol v2, which adds the extended receipt. A v2 adapter receiving a v1 request must return the v1 legacy shape, while a schema-v2 kernel may accept an old v1 legacy response during a controlled migration. In an extended receipt, normalize provider counters into Harness's canonical total `input_tokens`, then report `cache_read_input_tokens` and `cache_creation_input_tokens` as disjoint subsets; otherwise omit both rather than inventing zeroes. The resulting `UNKNOWN`, `REPORTED`, or `UNAVAILABLE` observation is advisory evidence, not a promise about cache hits, pricing, or retention.

`same-session` means a sequential continuation on the confirmed actual model and effort. `isolated-child` means a new context that receives a bounded `ROLE-PACKET.md`; this includes cross-model or cross-provider handoffs. Neither a requested alias nor a model change proves isolation, cache reuse, or independent review. Do not transfer a full conversation to make a child appear continuous.

## Project instruction adapters

`adapters/project/AGENTS.md.fragment` is the canonical short project entry point. It points to `.harness/INDEX.md` and the project-pinned `.harness/runtime/SKILL.md`, loading the full skill only on invocation. The pinned snapshot gives Codex, Claude, Gemini, and generic agents the same policy version even when their global installations differ.

- Codex and AGENTS.md-aware tools read `AGENTS.md` directly.
- Claude Code project `CLAUDE.md` contains `@AGENTS.md`.
- Gemini CLI project `GEMINI.md` contains `@./AGENTS.md`.
- A generic launcher points explicitly to `AGENTS.md` and the skill.

From a trusted full Harness package, use `skills/best-in-code/scripts/init_project.py` for a non-destructive setup. It always installs the canonical `AGENTS.md` block, adds requested provider importers, creates missing canonical files, and atomically installs one project-pinned skill snapshot. It preflights all sources and targets, rejects symlink/path escapes, preserves existing newline bytes, and never overwrites existing instruction content. If the pinned snapshot differs from a later package, it reports an update rather than silently mixing versions. If existing instructions conflict, show the conflict and obtain a human decision instead of choosing silently.

Legacy/mixed canonical schemas are never repaired piecemeal by initialization. From that same full package, use the preview-bound `skills/best-in-code/scripts/migrate_project.py` for the supported v1 layout and `skills/best-in-code/scripts/upgrade_project.py` for a newer pin plus only the delimited adapter blocks. Lifecycle scripts need the package's sibling manifests and `adapters/project/` sources; do not run their pinned copies from `.harness/runtime/scripts/`. The pinned `memory_ops.py` and workflow references are self-contained. A successful upgrade keeps the previous verified runtime under `.harness/runtime-history/`; a failed changed runtime is preserved under `.harness/runtime-recovery/` while the reviewed runtime is restored when safe.

For migration, preview with `--dry-run`, show the exact digest/archive/import plan, and apply only its matching human-approved digest. Preserve legacy inputs and IDs; active runs, conflicts, unsafe data, and unsupported layouts require resolution before mutation.

Keep `AGENTS.md` concise; required team rules belong there or in checked-in documents it links. Provider auto-memory is not a substitute for versioned instructions.

## Distribution

The shared `skills/best-in-code/` tree follows the Agent Skills layout and is the portable implementation. Package manifests are thin:

- `.codex-plugin/plugin.json` for Codex;
- `.claude-plugin/plugin.json` for Claude Code;
- `gemini-extension.json` for Gemini CLI.

The Claude Code plugin also declares host-enforced components: `agents/harness-qa.md` and `agents/harness-researcher.md` are read-only subagents whose fresh context backs the `agents.isolated` capability, and `hooks/hooks.json` installs a PreToolUse guard that refuses direct edits to `MEMORY.json`, `IDENTITY.json`, generated views, the pinned runtime, archives, and `.harness/.cache` ledgers, plus a SessionStart status line for projects that contain `.harness/`. Codex and Gemini receive the same policy as prose through the shared skill; only Claude Code enforces it mechanically today.

For the execution kernel, `anthropic_adapter.py` with the `ANTHROPIC-ADAPTER.json` template is the bundled real-provider adapter; see [execution-runtime.md](execution-runtime.md). Other providers still need a separately reviewed adapter that speaks the same closed protocol.

Validate the skill and each manifest independently. A manifest being present does not prove the corresponding CLI is installed, authenticated, or compatible; record actual validation results.

## No-filesystem models

If a model cannot read project files, it cannot provide durable cross-session project memory. Export the minimal current `INDEX`, verified record IDs, active state, and role packet through a user-controlled channel. Mark the session `DEGRADED`, prohibit canonical memory writes, and return proposed patches or records for human application.
