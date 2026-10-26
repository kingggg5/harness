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

## Project instruction adapters

`adapters/project/AGENTS.md.fragment` is the canonical short project entry point. It points to `.harness/INDEX.md` and the project-pinned `.harness/runtime/SKILL.md`, loading the full skill only on invocation. The pinned snapshot gives Codex, Claude, Gemini, and generic agents the same policy version even when their global installations differ.

- Codex and AGENTS.md-aware tools read `AGENTS.md` directly.
- Claude Code project `CLAUDE.md` contains `@AGENTS.md`.
- Gemini CLI project `GEMINI.md` contains `@./AGENTS.md`.
- A generic launcher points explicitly to `AGENTS.md` and the skill.

Team rules belong in `AGENTS.md` or checked-in documents it links; provider auto-memory does not replace versioned instructions.

## Init, doctor and identity

From a trusted full Harness package, `skills/best-in-code/scripts/init_project.py` sets up non-destructively: it installs the canonical `AGENTS.md` block and requested provider importers, creates missing canonical files and one project-pinned skill snapshot, and never overwrites existing instruction content. A pinned snapshot that differs from a later package is reported as an update, never silently mixed. If existing instructions conflict, show the conflict and obtain a human decision instead of choosing silently.

For an active delivery, check the canonical project surface: `IDENTITY.json`, `MEMORY.json`, `STATE.json`, `WORKFLOW.md`, `INDEX.md`, `CONFIG.md`, generated `CONTEXT.md`, `PREFERENCES.md` and `DECISIONS.md`, plus the pinned `runtime/`. Two memory/view files alone do not establish a valid active run. When some files already exist, inspect their identity/schema and run `harness doctor --project .` (or `python <package>/skills/best-in-code/scripts/memory_ops.py doctor --project .`) before choosing init, upgrade or migration. Do not repair mixed layouts or infer an active Run ID by writing replacement files.

If neither doctor command runs, use the same trusted package's other validation tools when executable; otherwise inspect read-only and report the missing validation capability. Do not install a replacement or reconstruct identity/run files to bypass it.

A changed remote/root/scope blocks memory recall and writes. `init_project.py --rebind-identity` is preview-bound (`--dry-run`, then `--approve <digest>`), requires an idle run, and preserves the Project ID for the same logical project; it never creates a fork identity. For a true fork, close the run, move the old `.harness/` to a human-selected external archive, then initialize the fork fresh so it receives a new Project ID. A byte-for-byte raw directory copy with identical VCS identity is not distinguishable automatically; disclose this limit.

## Migration and upgrade

Initialization never repairs legacy/mixed canonical schemas piecemeal. From the same full package, use the preview-bound `skills/best-in-code/scripts/migrate_project.py` for the supported v1 layout and `skills/best-in-code/scripts/upgrade_project.py` for a newer pin plus only the delimited adapter blocks. Preview with `--dry-run`, show the exact digest/archive/import plan, and apply only its matching human-approved digest. Preserve legacy inputs and IDs; active runs, conflicts, unsafe data, and unsupported layouts require resolution before mutation. Lifecycle scripts need the package's sibling manifests and `adapters/project/` sources, so never run their pinned copies from `.harness/runtime/scripts/`; the pinned `memory_ops.py` and workflow references are self-contained. A successful upgrade keeps the previous verified runtime under `.harness/runtime-history/`; a failed changed runtime is preserved under `.harness/runtime-recovery/` while the reviewed runtime is restored when safe.

## Distribution

`skills/best-in-code/` is the portable Agent Skills implementation; `.codex-plugin/plugin.json`, `.claude-plugin/plugin.json` and `gemini-extension.json` are thin manifests. A manifest's presence does not prove the corresponding CLI is installed, authenticated, or compatible; validate the skill and each manifest and record actual results.

On Claude Code, `hooks/hooks.json` installs a PreToolUse guard that denies Edit/Write/MultiEdit/NotebookEdit on canonical files (`MEMORY.json`, `IDENTITY.json`, generated views, the pinned runtime, archives, `.harness/.cache` ledgers). Shell writes are not intercepted, and Codex and Gemini get the policy only as prose.

## No-filesystem models

If a model cannot read project files, it cannot provide durable cross-session project memory. Export the minimal current `INDEX`, verified record IDs, active state, and role packet through a user-controlled channel. Mark the session `DEGRADED`, prohibit canonical memory writes, and return proposed patches or records for human application.
