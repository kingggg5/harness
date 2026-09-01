#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const MAX_UNPACKED_BYTES = 8 * 1024 * 1024;

function fail(message) {
	console.error(`Package verification failed: ${message}`);
	process.exit(1);
}

function readJson(path) {
	return JSON.parse(readFileSync(resolve(REPO_ROOT, path), "utf8"));
}

const packageManifest = readJson("package.json");
const adapterTemplate = readJson("skills/best-in-code/assets/templates/ADAPTER-ARGV.json");
const runContractTemplate = readJson("skills/best-in-code/assets/templates/RUN-CONTRACT.json");
const providerVersions = [
	readJson(".codex-plugin/plugin.json").version,
	readJson(".claude-plugin/plugin.json").version,
	readJson("gemini-extension.json").version,
].map((version) => version.split("+", 1)[0]);

for (const version of providerVersions) {
	if (version !== packageManifest.version) {
		fail(`provider version ${version} does not match package ${packageManifest.version}`);
	}
}
if (!Array.isArray(adapterTemplate) || adapterTemplate[0] !== "@harness-python") {
	fail("ADAPTER-ARGV.json must use @harness-python as its portable executable token");
}
const defaultVerifier = runContractTemplate.verifiers?.find((entry) => entry?.id === "test");
if (!Array.isArray(defaultVerifier?.argv) || defaultVerifier.argv[0] !== "@harness-python") {
	fail("RUN-CONTRACT.json default verifier must use @harness-python as its portable executable token");
}

const npmCli = process.env.npm_execpath;
if (!npmCli) {
	fail("npm CLI path is unavailable; run this gate with npm run pack:check");
}
const packed = spawnSync(process.execPath, [npmCli, "pack", "--dry-run", "--json", "--ignore-scripts"], {
	cwd: REPO_ROOT,
	encoding: "utf8",
	windowsHide: true,
});

if (packed.error) {
	fail(`could not run npm pack: ${packed.error.message}`);
}
if (packed.status !== 0) {
	fail(packed.stderr.trim() || `npm pack exited ${packed.status}`);
}

let report;
try {
	[report] = JSON.parse(packed.stdout);
} catch (error) {
	fail(`npm pack returned invalid JSON: ${error.message}`);
}

const files = new Set(report.files.map((entry) => entry.path.replaceAll("\\", "/")));
const requiredFiles = [
	".claude-plugin/plugin.json",
	".codex-plugin/plugin.json",
	"CHANGELOG.md",
	"LICENSE",
	"README.md",
	"RELEASING.md",
	"SECURITY.md",
	"adapters/project/AGENTS.md.fragment",
	"adapters/project/CLAUDE.md.fragment",
	"adapters/project/GEMINI.md.fragment",
	"adapters/project/GENERIC.md",
	"assets/brand/harness-logo.png",
	"assets/brand/harness-workflow.png",
	"bin/harness.js",
	"examples/README.md",
	"examples/cross-model-handoff.md",
	"examples/executable-agent-graph.md",
	"examples/full-product-feature.md",
	"examples/graph-engineering-feature.json",
	"examples/graph-engineering-feature.md",
	"examples/loop-engineering-performance.json",
	"examples/loop-engineering-performance.md",
	"examples/production-review.md",
	"examples/quick-bug-fix.md",
	"gemini-extension.json",
	"package.json",
	"scripts/check_eval_results.py",
	"scripts/check_eval_results_tests.py",
	"scripts/generate-sbom.mjs",
	"scripts/generate-sbom-tests.mjs",
	"scripts/launcher_tests.mjs",
	"scripts/verify-package.mjs",
	"skills/best-in-code/SKILL.md",
	"skills/best-in-code/assets/templates/LOOP-CONTRACT.json",
	"skills/best-in-code/assets/templates/RUN-CONTRACT.json",
	"skills/best-in-code/assets/templates/ADAPTER-ARGV.json",
	"skills/best-in-code/assets/templates/TASK-GRAPH.json",
	"skills/best-in-code/assets/templates/CONTEXT-MANIFEST.json",
	"skills/best-in-code/assets/templates/TOOL-REGISTRY.json",
	"skills/best-in-code/assets/evals/BEHAVIOR-SUITE.json",
	"skills/best-in-code/references/context-compiler.md",
	"skills/best-in-code/references/eval-runtime.md",
	"skills/best-in-code/references/execution-runtime.md",
	"skills/best-in-code/references/execution-isolation.md",
	"skills/best-in-code/references/graph-engineering.md",
	"skills/best-in-code/references/graph-runtime.md",
	"skills/best-in-code/references/loop-engineering.md",
	"skills/best-in-code/references/loop-runtime.md",
	"skills/best-in-code/scripts/bounded_json.py",
	"skills/best-in-code/scripts/context_compiler.py",
	"skills/best-in-code/scripts/context_eval_trace_tests.py",
	"skills/best-in-code/scripts/eval_matrix.py",
	"skills/best-in-code/scripts/execution_kernel.py",
	"skills/best-in-code/scripts/execution_runtime_tests.py",
	"skills/best-in-code/scripts/reference_adapter.py",
	"skills/best-in-code/scripts/trace_ops.py",
	"skills/best-in-code/scripts/loop_tests.py",
	"skills/best-in-code/scripts/loop_runtime.py",
	"skills/best-in-code/scripts/loop_runtime_tests.py",
	"skills/best-in-code/scripts/graph_tests.py",
	"skills/best-in-code/scripts/graph_runtime.py",
	"skills/best-in-code/scripts/graph_runtime_tests.py",
	"skills/best-in-code/scripts/validate_task_graph.py",
	"skills/best-in-code/scripts/validate_loop_contract.py",
];
const requiredPrefixes = [
	"skills/best-in-code/agents/",
	"skills/best-in-code/assets/evals/",
	"skills/best-in-code/assets/templates/",
	"skills/best-in-code/references/",
	"skills/best-in-code/scripts/",
];

for (const path of requiredFiles) {
	if (!files.has(path)) {
		fail(`required file is missing from archive: ${path}`);
	}
}
for (const prefix of requiredPrefixes) {
	if (![...files].some((path) => path.startsWith(prefix))) {
		fail(`required package area is empty: ${prefix}`);
	}
}

const packagedScripts = new Set([
	"scripts/check_eval_results.py",
	"scripts/check_eval_results_tests.py",
	"scripts/generate-sbom.mjs",
	"scripts/generate-sbom-tests.mjs",
	"scripts/launcher_tests.mjs",
	"scripts/verify-package.mjs",
]);
const forbidden = [...files].filter((path) =>
	path.startsWith(".git/") ||
	path.startsWith(".github/") ||
	path.startsWith("dist/") ||
	(path.startsWith("scripts/") && !packagedScripts.has(path)) ||
	path.includes("/__pycache__/") ||
	path.endsWith(".pyc") ||
	/(^|\/)(\.env|\.npmrc|[^/]+\.(key|pem|p12))$/i.test(path)
);
if (forbidden.length > 0) {
	fail(`private or build-only files entered the archive: ${forbidden.join(", ")}`);
}
if (report.unpackedSize > MAX_UNPACKED_BYTES) {
	fail(`archive expands to ${report.unpackedSize} bytes; limit is ${MAX_UNPACKED_BYTES}`);
}

console.log(
	`Package verified: ${packageManifest.name}@${packageManifest.version}; ` +
	`${files.size} files; ${report.size} packed bytes; ${report.unpackedSize} unpacked bytes.`
);
