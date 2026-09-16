# Decision Runtime

Use this reference when a workflow needs a typed semantic recommendation such as route, risk, research, parallelism, or human-review likelihood. It is a decision layer, not an executor.

Phase 1 is dependency-free and deterministic. It provides `bool`, `choice`, and `score` questions, bounded JSON input, a recommendation-only provider, and a repeatable evaluation report. A future local or external provider must implement the same schema and remain optional; it must not add PyTorch, Transformers, model downloads, or a GPU dependency to the Harness core package.

## Contract

Questions are a closed JSON document:

```json
{
	"schema_version": 1,
	"questions": [
		{"id": "route", "type": "choice", "options": ["quick", "standard", "full"]},
		{"id": "needs_human", "type": "bool"},
		{"id": "risk", "type": "score", "minimum": 0, "maximum": 1}
	]
}
```

The decision result contains typed values, probabilities or confidence, input digests, and `recommendation_only: true` plus `policy_authority: false`. It also includes a deterministic `policy_recommendation` safety floor: low confidence, a human recommendation, high risk, or high security risk produces `HUMAN_REQUIRED`. This remains advisory; it never grants a tool, changes a route, bypasses an approval, mutates memory, or executes a command. The execution kernel and human gate make the authoritative decision.

## Commands

```bash
harness decide \
	--state state.json \
	--questions questions.json \
	--json

harness decision-eval \
	--suite .harness/runtime/assets/evals/DECISION-SUITE.json \
	--trials 3 \
	--json
```

The bundled `DECISION-SUITE.json` is a smoke benchmark for the deterministic provider, not evidence of live-model quality. `DECISION-REPRESENTATIVE-SUITE.json` adds 20 manually labeled easy, medium, risky, research, scale, and parallel tasks as a local baseline. Reports include accuracy, macro F1, Brier score, expected calibration error, normalized score error, mean/p95 latency, decisions per second, and process RSS when the host exposes it. These labels are a Harness baseline, not user or production ground truth; compare providers only on the same cases, labels, task revision, and environment.

## Routing boundary

Use the decision output to reduce unnecessary frontier calls, for example by recommending `quick` for a one-file typo or `full` for a production migration. The policy floor turns uncertain or risky recommendations into `human_approval`; it does not execute that approval. The router still validates capabilities, scope, budgets, context boundary, and human gates. A high probability is never permission to deploy, delete, publish, spend money, expose data, or skip QA.

Unknown or unsupported semantic decisions remain explicit. Do not turn a missing provider, missing telemetry, or low-confidence result into a confident default; use the deterministic fallback or ask the human when the decision is material.

## Future providers

An ONNX/CPU provider can be added under an optional adapter after representative labeled evaluation proves its value. Keep training, model files, quantization, and provider-specific dependencies outside the core package. Release evidence must report held-out accuracy, calibration, latency, RSS, failure behavior, and policy-ablation results; a small model is not automatically cheaper or safer.
