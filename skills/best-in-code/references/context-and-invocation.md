# Context boundaries and reliable skill loading

Load this for a skill dependency, user-only invocation, a handoff/resume, or a decision about which context a next phase needs. Discovery metadata, actual loading and user authorization must all match before a workflow can execute.

## Actually load a dependency

Use the host's real loading mechanism: a Skill tool by registered name, or reading the announced `SKILL.md` or local reference. Never invent a Skill tool, command, plugin, credential or agent type.

Respect the target skill's invocation setting and current user authorization. Never dispatch a user-only skill as a hidden dependency; surface the need to the user only when it blocks the task, otherwise use the authorized local workflow. Do not ask for setup merely because a recipe assumes a tracker or another skill: repository evidence, local artifacts and the existing capability fallback often suffice.

## Preserve the decision, not the whole transcript

At a phase boundary, prefer continuing when the current reasoning and evidence are still needed, and read only the sources the next phase needs. A bounded authorized pass in a separate context gets a role packet from `assets/templates/ROLE-PACKET.md`.

A cross-provider, cross-directory or colleague handoff needs portable evidence: project/run binding, objective, approved decisions and why, current diff/commit, performed checks, open questions, exact next action and source locations. Redact secrets and avoid raw retrieval dumps. Follow [model-routing.md](model-routing.md) for the context-boundary labels and model authorization.

Provider compaction may happen anyway, so keep enough explicit scoped state to resume. Preserve the active decision and primary evidence pointers rather than an undirected summary, and verify them before continuing a mutation. Do not hardcode a context threshold, clear context automatically, or recommend compaction merely to save tokens.

## Keep project vocabulary compatible

Use the repository's vocabulary (`GLOSSARY.md`, ADRs, domain docs) where it prevents ambiguity. Never rename canonical `CONTEXT.md`, create a duplicate knowledge store, or create a glossary just because another skill collection uses one.
