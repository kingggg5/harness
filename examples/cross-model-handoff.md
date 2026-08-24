# Cross-model handoff

Use this to assign different model profiles without turning chat history into project authority.

## Start in Codex or another planning-capable provider

```text
Harness standard with adaptive model routing: Plan and implement cursor pagination for the audit log. Preserve the existing response envelope. Record verified constraints and stop after the plan gate so another provider can continue.
```

## Continue in Claude Code or Gemini CLI

```text
Harness resume
```

The second provider validates repository identity, runtime pin, current `run_id`, state, approvals, and scoped records before continuing. It does not trust a prose handoff by itself.

## Review with a separate model

```text
Harness review: Check the pagination change for skipped or duplicated records, cursor tampering, authorization drift, query cost, and missing regression tests. Do not modify files.
```

An independent review is claimed only if the reviewer was isolated from implementation context. Otherwise Harness records a separate labeled review pass, not false independence.
