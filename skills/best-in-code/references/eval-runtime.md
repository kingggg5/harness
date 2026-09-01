# Behavioral eval matrix and trace operations

Tests prove deterministic code paths. Behavioral evals measure whether the whole harness still produces the intended task outcome while obeying policy, routing tools correctly, and retaining the right context under repeated trials.

The bundled suite includes three illustrative safety cases across `single-owner`, `full`, and `ablation` variants. Fixture data proves the evaluator itself and makes the expected direction explicit; it is not evidence that a live model achieved those numbers.

```bash
harness eval-matrix \
	--suite .harness/runtime/assets/evals/BEHAVIOR-SUITE.json \
	--variant full \
	--trials 3 \
	--concurrency 3 \
	--json
```

For real measurements, pass an exact JSON argv array with `--local-runner-argv` or `--external-runner-argv`. The evaluator never invokes a shell. It sends one bounded JSON request on stdin and expects one closed-schema observed result on stdout. External cases skip transparently unless `--require-external` is set. Reports include pass rates plus mean and p95 latency, tokens, cache use, cost, retries, context bytes, and maximum tool output.

Use ablation to remove one harness layer and test causal value. A failing ablation is often the intended result; do not weaken expectations to make the overall matrix green. CI should select the production variant and keep comparison reports as evidence.

## Trace operations

The execution kernel writes the shared trace schema. Operate on it without executing recorded actions:

```bash
harness trace validate --trace .harness/.cache/execution-runs/.../trace.jsonl --json
harness trace timeline --trace .harness/.cache/execution-runs/.../trace.jsonl --limit 100 --json
harness trace inspect --trace .harness/.cache/execution-runs/.../trace.jsonl --sequence 4 --json
harness trace redact --trace input.jsonl --output redacted.jsonl --json
harness trace replay --trace input.jsonl --limit 1000 --json
```

Validation checks closed fields, bounds, canonical JSON, sequence, trace identity, timestamps, payload shape, and the full SHA-256 chain. Redaction removes common secrets and personal data, then reseals the derived chain. Replay creates an evidence-only plan with every action marked `NOT_EXECUTED`; it never calls a tool, writes, runs a command, or accesses the network.

Treat the trace as integrity evidence, not authenticity proof. Anyone who can replace the whole local trace and state can recompute an unsigned chain. Release attestations protect distributed package provenance; a trusted external sink or signature is still required for adversarial runtime non-repudiation.
