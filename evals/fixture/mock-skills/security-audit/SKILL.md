---
name: security-audit
description: "Security and production-readiness review checklist for diffs and services: injection, path traversal, authorization, secrets, data handling. Use when reviewing changes or before release."
---

# Security Audit

Check the diff for: path traversal and unsafe file paths; injection (SQL, shell, CSV/formula); missing authorization; secret exposure; unsafe deserialization; data-loss edge cases.

Report each security finding as `SEC-<n>: <file>:<line> <issue> — <fix>`.
