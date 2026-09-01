#!/usr/bin/env node

const { spawnSync } = require("node:child_process");
const path = require("node:path");
const fs = require("node:fs");

const SCRIPTS = path.join(__dirname, "..", "skills", "best-in-code", "scripts");
const PACKAGE_JSON = path.join(__dirname, "..", "package.json");
let packageVersion = "unknown";
try {
	const version = require(PACKAGE_JSON).version;
	packageVersion = typeof version === "string" && version ? version : packageVersion;
} catch {
	// The later package-integrity check supplies the actionable reinstall error.
}

const PROJECT_SCRIPTS = {
	init: { script: "init_project.py", prefix: [] },
	migrate: { script: "migrate_project.py", prefix: [] },
	upgrade: { script: "upgrade_project.py", prefix: [] },
	portability: { script: "validate_portability.py", prefix: [] },
	"loop-validate": { script: "validate_loop_contract.py", prefix: [] },
	"loop-run": { script: "loop_runtime.py", prefix: [] },
	"graph-validate": { script: "validate_task_graph.py", prefix: [] },
	"graph-run": { script: "graph_runtime.py", prefix: [] },
	run: { script: "execution_kernel.py", prefix: ["run"] },
	"run-validate": { script: "execution_kernel.py", prefix: ["validate"] },
	"run-status": { script: "execution_kernel.py", prefix: ["status"] },
	"run-approve": { script: "execution_kernel.py", prefix: ["approve"] },
	"run-cancel": { script: "execution_kernel.py", prefix: ["cancel"] },
	"run-trace-verify": { script: "execution_kernel.py", prefix: ["verify-trace"] },
	"context-build": { script: "context_compiler.py", prefix: ["compile"] },
	"tools-validate": { script: "context_compiler.py", prefix: ["validate-tools"] },
	"eval-matrix": { script: "eval_matrix.py", prefix: [] },
	trace: { script: "trace_ops.py", prefix: [] },
	evals: { script: "run_memory_evals.py", prefix: [] },
	race: { script: "race_tests.py", prefix: [] },
};

const MEMORY_COMMANDS = new Set([
	"remember", "correct", "forget", "recall", "status", "doctor",
	"render", "export-cache", "close-run", "mem-validate",
]);

const USAGE = `Harness ${process.env.npm_package_version || packageVersion} — executable delivery graphs with durable project memory

Usage:
  npx github:kingggg5/harness <command> [args...]

Project lifecycle:
  init        Initialize .harness/ for a project      (--project DIR --models all)
  migrate     Preview/apply legacy v1 migration       (--dry-run, --approve SHA256)
  upgrade     Preview/apply runtime pin upgrade       (--dry-run, --approve SHA256)
  portability Validate the installed package layout
  loop-validate Validate a bounded LOOP-CONTRACT.json (--contract PATH, --json)
  loop-run    Supervise bounded loop receipts          (start|status|trigger|claim|finish|pause|resume|cancel|recover)
  graph-validate Validate a bounded TASK-GRAPH.json     (--graph PATH, --json)
  graph-run   Record/resume graph node receipts         (start|status|resume|claim|finish|recover)
  run         Execute/resume a capability-bounded agent graph
  run-validate | run-status | run-approve | run-cancel | run-trace-verify
  context-build Compile bounded, provenance-rich task context
  tools-validate Validate a closed capability/tool registry
  eval-matrix Run full/single-owner/ablation behavior trials
  trace       Validate, inspect, redact, or dry-run replay of a trace

Memory operations (memory_ops.py):
  remember | correct | forget | recall | status | render
  export-cache | close-run | mem-validate
  doctor      One-shot project health report

Quality gates:
  race        Two-process race regression suite
  evals       M01-M41 memory evaluation matrix

All arguments are passed through unchanged to the underlying script.
Examples:
  npx github:kingggg5/harness init --project . --models all
  npx github:kingggg5/harness doctor --project .
  npx github:kingggg5/harness loop-validate --contract .harness/LOOP-CONTRACT.json
  npx github:kingggg5/harness loop-run status --project . --contract .harness/LOOP-CONTRACT.json
  npx github:kingggg5/harness graph-validate --graph .harness/TASK-GRAPH.json
  npx github:kingggg5/harness graph-run status --project . --graph .harness/TASK-GRAPH.json
  npx github:kingggg5/harness run --project . --contract .harness/RUN-CONTRACT.json --adapter-argv-file .harness/ADAPTER-ARGV.json
  npx github:kingggg5/harness context-build --project . --task "Fix checkout race" --include src/checkout.ts
  npx github:kingggg5/harness eval-matrix --suite skills/best-in-code/assets/evals/BEHAVIOR-SUITE.json --variant full --json
  npx github:kingggg5/harness close-run --project . --run-id RUN-7f3a`;

function pathEnvironmentName(environment) {
	return Object.keys(environment).find((name) => name.toUpperCase() === "PATH") || "PATH";
}

function absolutePathOnly(environment) {
	const name = pathEnvironmentName(environment);
	return {
		name,
		value: String(environment[name] || "")
			.split(path.delimiter)
			.filter((entry) => entry && path.isAbsolute(entry))
			.join(path.delimiter),
	};
}

function probePython(candidate, environment) {
	const probe = spawnSync(candidate, [
		"-B",
		"-c",
		"import os, sys; executable=os.path.realpath(sys.executable); print(executable); raise SystemExit(0 if sys.version_info >= (3, 12) and os.path.isabs(executable) and os.path.isfile(executable) else 1)",
	], {
		cwd: SCRIPTS,
		encoding: "utf8",
		env: {
			...environment,
			PYTHONDONTWRITEBYTECODE: "1",
			PYTHONIOENCODING: environment.PYTHONIOENCODING || "utf-8",
		},
		timeout: 5000,
		maxBuffer: 8192,
		windowsHide: true,
	});
	if (probe.status !== 0) return null;
	const lines = probe.stdout.trim().split(/\r?\n/).filter(Boolean);
	if (lines.length !== 1 || !path.isAbsolute(lines[0])) return null;
	try {
		const resolved = fs.realpathSync(lines[0]);
		return fs.statSync(resolved).isFile() ? resolved : null;
	} catch {
		return null;
	}
}

function resolvePython() {
	const explicit = process.env.HARNESS_PYTHON;
	if (explicit) {
		if (!path.isAbsolute(explicit)) {
			return { python: null, error: "HARNESS_PYTHON must be an absolute Python 3.12+ executable path." };
		}
		const python = probePython(explicit, process.env);
		return python
			? { python, error: "" }
			: { python: null, error: "HARNESS_PYTHON is not an executable Python 3.12+ interpreter." };
	}
	const safePath = absolutePathOnly(process.env);
	const environment = { ...process.env, [safePath.name]: safePath.value };
	for (const candidate of ["python3", "python", "py"]) {
		const python = probePython(candidate, environment);
		if (python) return { python, error: "" };
	}
	return {
		python: null,
		error: "Harness requires Python 3.12+ on an absolute PATH entry; set HARNESS_PYTHON to an absolute executable path to pin one.",
	};
}

function main() {
	const [command, ...rest] = process.argv.slice(2);
	if (!command || command === "--help" || command === "-h") {
		console.log(USAGE);
		process.exit(command ? 0 : 1);
	}

	let script;
	let args = rest;
	if (MEMORY_COMMANDS.has(command)) {
		script = "memory_ops.py";
		const inner = command === "mem-validate" ? "validate" : command;
		args = [inner, ...rest];
	} else if (PROJECT_SCRIPTS[command]) {
		const target = PROJECT_SCRIPTS[command];
		script = target.script;
		args = [...target.prefix, ...rest];
	} else {
		console.error(`Unknown command: ${command}\n`);
		console.error(USAGE);
		process.exit(1);
	}

	const resolution = resolvePython();
	if (!resolution.python) {
		console.error(resolution.error);
		process.exit(1);
	}
	const python = resolution.python;

	const result = spawnSync(python, ["-B", path.join(SCRIPTS, script), ...args], {
		stdio: "inherit",
		env: {
			...process.env,
			PYTHONIOENCODING: process.env.PYTHONIOENCODING || "utf-8",
			PYTHONDONTWRITEBYTECODE: "1",
		},
	});
	if (result.error) {
		console.error(`Failed to launch ${python}: ${result.error.message}`);
		process.exit(1);
	}
	process.exit(result.status ?? 1);
}

if (require.main === module && fs.existsSync(path.join(SCRIPTS, "memory_ops.py"))) {
	main();
} else {
	console.error("Harness package files are missing; reinstall the package.");
	process.exit(1);
}
