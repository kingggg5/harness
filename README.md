# Harness

Harness is an adaptive software-delivery skill for Codex, Claude Code, Gemini CLI, and filesystem-capable AI agents. One portable skill routes tasks through quick, standard, or full delivery; seven logical role contracts; scoped project memory; evidence-based QA; and human gates.

## Use

```text
Harness: implement this feature
Harness full: investigate and fix this production-risk bug
Harness review: review the current changes
Harness resume
Harness remember project: use repository formatter settings
Harness memory status
```

Codex can invoke `$best-in-code`. Claude Code plugins expose `/harness:best-in-code`. Gemini and generic agents can use the natural form or their discovered skill command.

## Provider setup

| Provider | Local package setup | Invoke |
|---|---|---|
| Codex | Add or update `harness` from the configured personal marketplace, then start a new task | `$best-in-code <task>` |
| Claude Code | `claude --plugin-dir <harness-package>` for local development, or install through a Claude marketplace | `/harness:best-in-code <task>` |
| Gemini CLI | `gemini extensions link <harness-package>` for local development, or `gemini extensions install <source>` | Ask Gemini to use `best-in-code` |
| Generic agent | Make the package readable and add the project adapter | `Harness: <task>` |

Restart or open a fresh provider session after installing or updating so skill discovery and manifests reload.

## Initialize a project

From this package:

```text
python skills/best-in-code/scripts/init_project.py --project <project> --models all --dry-run
python skills/best-in-code/scripts/init_project.py --project <project> --models all
```

The initializer creates only missing `.harness/` files, pins a verified snapshot of the portable skill under `.harness/runtime/`, always installs the canonical `AGENTS.md` block, and appends provider imports without overwriting existing `AGENTS.md`, `CLAUDE.md`, or `GEMINI.md` content. The snapshot keeps every model on the same Harness version until a human-reviewed update.

Validate the package:

```text
python skills/best-in-code/scripts/validate_portability.py
python skills/best-in-code/scripts/run_memory_evals.py --json
python skills/best-in-code/scripts/race_tests.py
```

`race_tests.py` spawns real two-process races (contention against a held lock, crash-orphan recovery, concurrent writer storm, path-alias convergence, permission-denied lock open, identity/digest binding, exact run ownership, recall ceilings) and must pass on every supported platform before release; M39-M41 memory evals stay red until external-model oracles are wired.

Provider auto-memory and semantic search are optional. Plain `.harness/` files remain canonical so a different model can resume the same project.

## Safe migration and upgrades

The initializer refuses legacy or mixed schemas instead of creating a half-upgraded project. For the supported Markdown v1 layout, preview first and apply only the exact digest you reviewed:

```text
python skills/best-in-code/scripts/migrate_project.py --project <project> --models all --dry-run --json
python skills/best-in-code/scripts/migrate_project.py --project <project> --models all --approve <sha256-from-preview> --json
```

Migration archives the original inputs byte-for-byte under `.harness/migrations/`, imports safe structured records, maps legacy IDs in `MIGRATION.json`, updates managed adapter blocks, pins the current runtime, validates the result, and rolls back on failure. Active legacy runs, conflicts, unsafe memory, unsupported command rows, and unknown mixed layouts stop for human review.

The approval digest is bound to the canonical target path, deterministic repository identity, reviewed input bytes, selected adapter fragments, and bundled runtime. Moving or forking the project, changing its Git identity, or changing the package requires a fresh preview. Migration replaces only exact known legacy whole-file launchers or one unambiguous managed block; custom unmarked instructions stop for a manual merge.

When the package reports a newer pinned runtime, use the same preview-bound pattern:

```text
python skills/best-in-code/scripts/upgrade_project.py --project <project> --models all --dry-run --json
python skills/best-in-code/scripts/upgrade_project.py --project <project> --models all --approve <sha256-from-preview> --json
```

The prior verified runtime remains recoverable under `.harness/runtime-history/`.

## Deterministic memory operations

Natural `Harness remember/correct/forget/recall` commands are previewed by the agent. The executable, provider-neutral core is `skills/best-in-code/scripts/memory_ops.py`; it supports `remember`, `correct`, `forget`, `recall`, `status`, `doctor`, `validate`, `render`, `export-cache`, and `close-run`. Run `close-run --run-id <exact-current-run-id>` at completion so task-only records cannot survive into another run.

Every mutating command is previewed first in conversation; task scope requires `--run-id` matching `STATE.json` exactly; recall budgets are capped (`--max-records 1..100`, `--max-bytes 256..131072`). All output is JSON.

Quick reference (run from any directory; `--project` defaults to `.`):

```text
memory_ops.py remember --scope project --kind fact --key K --value V
memory_ops.py remember --scope task --kind decision --key K --value V --run-id R
memory_ops.py correct <RECORD_ID> [--value V]      memory_ops.py forget <RECORD_ID>
memory_ops.py close-run --run-id R                 memory_ops.py recall --query "text"
memory_ops.py status                               memory_ops.py validate
memory_ops.py render                               memory_ops.py export-cache --out PATH
memory_ops.py doctor
```

`doctor` is the one-shot health report: identity validity and repository drift, store schema plus duplicate-active-tuple conflicts, run state (idle INTAKE is healthy), derived-view freshness against canonical memory, runtime pin presence, writer-lock availability, and cache state. Exit 0 with `verdict: HEALTHY` means the project is safe to resume.
