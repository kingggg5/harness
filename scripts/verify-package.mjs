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
	"adapters/project/AGENTS.md.fragment",
	"adapters/project/CLAUDE.md.fragment",
	"adapters/project/GEMINI.md.fragment",
	"adapters/project/GENERIC.md",
	"assets/brand/harness-logo.png",
	"assets/brand/harness-workflow.png",
	"bin/harness.js",
	"examples/README.md",
	"examples/cross-model-handoff.md",
	"examples/full-product-feature.md",
	"examples/graph-engineering-feature.json",
	"examples/graph-engineering-feature.md",
	"examples/loop-engineering-performance.json",
	"examples/loop-engineering-performance.md",
	"examples/production-review.md",
	"examples/quick-bug-fix.md",
	"gemini-extension.json",
	"package.json",
	"skills/best-in-code/SKILL.md",
	"skills/best-in-code/assets/templates/LOOP-CONTRACT.json",
	"skills/best-in-code/assets/templates/TASK-GRAPH.json",
	"skills/best-in-code/references/execution-isolation.md",
	"skills/best-in-code/references/graph-engineering.md",
	"skills/best-in-code/references/graph-runtime.md",
	"skills/best-in-code/references/loop-engineering.md",
	"skills/best-in-code/references/loop-runtime.md",
	"skills/best-in-code/scripts/bounded_json.py",
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

const forbidden = [...files].filter((path) =>
	path.startsWith(".git/") ||
	path.startsWith(".github/") ||
	path.startsWith("dist/") ||
	path.startsWith("scripts/") ||
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
