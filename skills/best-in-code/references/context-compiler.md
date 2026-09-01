# Context compiler and tool contracts

Use the context compiler for standard/full work, multi-module onboarding, handoffs, resumed runs, or any task where “load the whole repository” would be noisy or unsafe. Quick work can keep a small inspected context without writing a manifest.

The compiler produces one deterministic JSON object with bounded selected content, provenance, trust labels, exclusion reasons, prompt-injection quarantine, budget use, and an integrity digest. It searches only project-relative regular text files, skips links and common generated/vendor directories, bounds Git commands, and never runs repository code.

```bash
harness context-build \
	--project . \
	--task "Fix the checkout idempotency race" \
	--include src/checkout.ts \
	--symbol finalizeCheckout \
	--verification .harness/evidence/reproduction.json \
	--output .harness/.cache/checkout-context.json
```

Selection order is deliberately narrow:

1. Applicable project instruction files are trusted control supplied by the project owner.
2. Canonical Harness memory is untrusted data until its records are re-verified.
3. Explicit includes, requested symbol matches, task-relevant paths, Git status/diff, and verification files are untrusted data or evidence.
4. High-confidence prompt-injection patterns in non-control content are quarantined: their metadata and digest remain visible, but their text does not enter selected context.

The cache key binds compiler version, task, Git commit, limits, selection diagnostics, and the actual selected/quarantined source digests. A dirty or untracked source-byte change therefore changes the key even when `HEAD` does not.

The compiler does not decide correctness, grant a tool, or turn retrieved text into policy. The execution layer must re-check authorization at the moment of use.

## Tool registry

`TOOL-REGISTRY.json` is the richer design-time contract for a tool backend. It closes the input/output JSON schemas and records when to use it, when not to use it, prohibitions, scopes, effect class, approval class, timeout, pagination/output caps, digest fields, idempotency, and redacted telemetry.

```bash
harness tools-validate --registry .harness/TOOL-REGISTRY.json --json
```

Write/external/destructive tools fail validation unless they have the required approval and idempotency policy. The executable `RUN-CONTRACT.json` contains the smaller runtime-enforced capability view. Keep the two aligned, but do not treat a documentation registry as runtime authorization.

