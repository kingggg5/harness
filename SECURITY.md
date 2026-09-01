# Security Policy

## Supported versions

Security fixes are made on the latest released minor version. Older versions should be upgraded before a report is reproduced.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting for `kingggg5/harness` when it is available. Do not open a public issue containing credentials, exploit payloads, private repository data, or a working path to a destructive action.

Include the affected version, operating system, trust boundary, minimal reproduction, expected policy, observed result, and whether any external effect occurred. Redact tokens, personal data, project content, and provider responses.

Harness treats model output, retrieved context, skills, tool results, worker messages, and memory candidates as untrusted data. A report is especially useful when it demonstrates one of these classes:

- a tool call executes outside its declared capability, path, command, network, or budget scope;
- an approval, idempotency key, claim, trace, or project/run binding can be replayed or crossed;
- prompt injection becomes policy or durable trusted memory;
- a secret enters a prompt, trace, package, release asset, or worker sandbox;
- path aliases, links, races, or stale state bypass fail-closed behavior.

Do not test against repositories, accounts, providers, or services you do not own or have permission to assess.
