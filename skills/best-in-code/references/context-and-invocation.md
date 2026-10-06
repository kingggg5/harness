# Context boundaries and reliable skill loading

Load this for a skill dependency, user-only invocation, a handoff/resume, or a decision about which context a next phase needs. Discovery metadata, actual loading and user authorization must all match before a workflow can execute.

## Actually load a dependency

Naming `/some-skill` in prose is not proof that its instructions loaded. Check the host's available skill catalog, select the real supported entry and use that host's loading mechanism. If it exposes a Skill tool, invoke a supported skill by its registered name. For Codex filesystem skills, read the announced `SKILL.md`; read a local Harness reference directly when the router says its condition applies. Do not invent a Skill tool, command, plugin, credential or agent type.

Respect the target skill's explicit invocation setting and current user authorization. A user-only skill must not be dispatched as a hidden dependency; surface the need to the user only when it blocks the task, otherwise use the authorized local workflow. Do not ask for setup merely because a recipe assumes a tracker or another skill: repository evidence, local artifacts and the existing capability fallback often suffice.

Check each handoff against the implementation it names. When a bug workflow ends with verification and cleanup, its router/docs must not say that it automatically runs a separate retrospective or architecture skill. Remove stale executable handoffs; express an evidence-backed optional follow-up as a recommendation and keep the user's scope explicit.

Harness remains one normally discoverable skill. Preserve `allow_implicit_invocation: true` unless the user explicitly changes it. Reusable workflow references are conditionally loaded; they do not become extra user-only setup commands. Keep YAML frontmatter valid, quote descriptions containing colon-space, and keep description/UI metadata aligned with actual trigger scope.

## Preserve the decision, not the whole transcript

At a phase boundary, prefer continuing when the current reasoning and evidence are still needed. Read only the relevant sources for the next phase. If a bounded authorized pass benefits from separate context, give it a role packet with objective, exclusions, current revision, owned scope, source pointers, acceptance, verification and stop conditions.

A cross-provider, cross-directory or colleague handoff needs portable evidence: project/run binding, objective, approved decisions and why, current diff/commit, performed checks, open questions, exact next action and source locations. Redact secrets and avoid raw retrieval dumps. Follow [model-routing.md](model-routing.md) for the context-boundary labels and model authorization.

Provider compaction may happen automatically; the skill cannot prevent it by saying to keep a window unbroken. Maintain enough explicit scoped state to resume safely. When compaction or a new context is needed, preserve the active decision/problem and primary evidence pointers rather than an undirected summary. Verify them before continuing a mutation. Do not hardcode an assumed model context threshold, clear context automatically, or recommend compaction merely to save tokens.

## Keep project vocabulary compatible

Read an existing project `GLOSSARY.md`, ADR directory or domain document only where it prevents ambiguity. Use the repository's vocabulary in specs, tests, slice packets and reviews. Do not rename canonical Harness `CONTEXT.md`, introduce a duplicate generic knowledge store, or create a glossary just because another skill collection uses one. The generated readable memory view remains bound to `MEMORY.json`; optional reusable topology/glossary belongs in the existing project-map convention.

## Write pointers that will fire

A pointer names both the material and the condition for reading it. Keep unconditional entrypoint rules short; put details behind the condition that needs them. Keep one authoritative procedure for an operation, and keep explanations next to the relevant condition. Removing a useful detail solely for length is not an improvement; retain what changes behavior and drop duplication or stale facts. Never promote a local example or another author's preferred workflow into a universal gate.
