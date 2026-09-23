# Jev Engineering and Best Combos

This guide preserves the earlier Jev strengths/limits, research grounding and combo recipes while labeling integrations that are not shipped. Use [jev-runtime.md](jev-runtime.md) for executable behavior and setup; use [async-operation-runtime.md](async-operation-runtime.md) for Unreal Agent operations, cache affinity, bounded outputs and migration tradeoffs.

## The original Jev design ideas

Jev is a hosted typed-decision model for choices, scores and binary probability questions. The original playbook recommends it for bounded ranking, relevance, filtering and rule questions, and warns against relying on parametric memory for changing third-party APIs. Claims about sub-200 ms latency are from that earlier note, not a Harness guarantee. Jev confidence is useful input to a deterministic threshold, not proof.

The zero-KV-cache thought experiment asks what context each model turn truly needs. The ten ideas in the older note are: separate writing from execution/decision; build context per query; price context transfer in model routing; measure reads/search separately from edits; select hide/short/long/full visibility; disclose tool schemas on demand; pin conditional instructions; route by data trust; share read-only retrieval where useful; inspect scripts before execution.

Harness `0.7.1` implements these selectively and opt-in through schema-v3. Exact support and limitations live in the runtime guide; no single combo below should be assumed active just because it appears here.

## Original combo recipes

| Combo | Earlier idea | Current Harness status |
| --- | --- | --- |
| Jev + Exa/WebSearch | Ground a question in retrieved docs/issues, then rank evidence with typed Jev choices | Exa/Tavily are not integrated. Public search results can be reviewed externally and supplied as public, provenance-labelled evidence. |
| Jev + Gemini/writer model | Writer handles planning/code; Jev handles bounded selection and classification | The pattern is provider-neutral. Harness ships an Anthropic adapter and generic profiles, not an automatic Gemini/Codex API adapter. Model names in older notes are historical examples; verify current model and rate cards. |
| Jev + `fast-jev-compaction` | Keep tool-call/result pairs and original evidence; prune only the model-facing history | The source was inspected at commit `e3f262a7f4d42bd8dd32ced30d26176f7cb545b0`; no dependency was added. Harness uses its own bounded context and durable ledger. |
| Jev + CUA/Browser Use | Observe real UI elements, choose a bounded action, verify visible results | Neither CUA nor Browser Use is connected to this plugin. They remain optional design references. |
| Jev + Unreal Agent | Run durable, versioned operations asynchronously while the coordinator remains responsive | Source was inspected at `b7c9bf1c5c2fa4127255c07727a7c8413e23944a`; the pattern is documented, not ported. Harness `run` still executes pending calls sequentially. |

The original playbook's cross-repository matrix named Gemini 2.5 Pro/Flash, Claude Opus 4/Sonnet 4, GPT-4.5/o3, Ollama/vLLM/DeepSeek R1, Exa and Tavily. These remain historical examples, not current bindings or bundled connectors. Local inference may avoid a provider API bill but still has hosting and compute cost. CUA, Browser Use and MCP servers require separate installation, permissions and security review.

The earlier playbook also named `tools/jev-assistant.mjs` with `gate`, `compress` and `preflight` commands for a different project. That script is not in Harness. Use `turn-build`, `tools-disclose`, `route-cost`, and registered verifier policies for the capabilities that do exist.

## Trust, cost and evidence

Jev requests use the hosted TypeSafe API. The default schema-v3 path selects chunks locally. `jev-public` is opt-in and requires an explicit sensitivity policy that classifies every transmitted chunk as public; the task text itself must also be public. Jev cannot approve tools or replace execution-time authorization.

The earlier Opus/Sonnet cost calculation and the reported `56.2%`/`46.5%` retrieval figures are examples or external-study findings, not current Harness billing data. Unreal Labs' “up to 40%” is a vendor-reported benchmark. Harness must compare provider-reported token/cache counters and task/policy success on the same workload before claiming savings.

For exact setup, public-data controls, and migration boundaries, see [jev-runtime.md](jev-runtime.md) and [async-operation-runtime.md](async-operation-runtime.md).
