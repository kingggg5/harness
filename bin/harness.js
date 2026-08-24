#!/usr/bin/env node

const { spawnSync } = require("node:child_process");
const path = require("node:path");
const fs = require("node:fs");

const SCRIPTS = path.join(__dirname, "..", "skills", "best-in-code", "scripts");

const PROJECT_SCRIPTS = {
	init: "init_project.py",
	migrate: "migrate_project.py",
	upgrade: "upgrade_project.py",
	portability: "validate_portability.py",
	evals: "run_memory_evals.py",
	race: "race_tests.py",
};

const MEMORY_COMMANDS = new Set([
	"remember", "correct", "forget", "recall", "status", "doctor",
	"render", "export-cache", "close-run", "mem-validate",
]);

const USAGE = `Harness ${process.env.npm_package_version || "0.4.1"} — adaptive delivery skill with durable project memory

Usage:
  npx github:kingggg5/harness <command> [args...]

Project lifecycle:
  init        Initialize .harness/ for a project      (--project DIR --models all)
  migrate     Preview/apply legacy v1 migration       (--dry-run, --approve SHA256)
  upgrade     Preview/apply runtime pin upgrade       (--dry-run, --approve SHA256)
  portability Validate the installed package layout

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
  npx github:kingggg5/harness close-run --project . --run-id RUN-7f3a`;

function resolvePython() {
	const candidates = [process.env.HARNESS_PYTHON, "python3", "python", "py"].filter(Boolean);
	for (const candidate of candidates) {
		const probe = spawnSync(candidate, ["-c", "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)"], { encoding: "utf8" });
		if (probe.status === 0) return candidate;
	}
	return null;
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
		script = PROJECT_SCRIPTS[command];
	} else {
		console.error(`Unknown command: ${command}\n`);
		console.error(USAGE);
		process.exit(1);
	}

	const python = resolvePython();
	if (!python) {
		console.error("Harness requires Python 3.12+ on PATH (tried HARNESS_PYTHON, python3, python, py).");
		process.exit(1);
	}

	const result = spawnSync(python, [path.join(SCRIPTS, script), ...args], {
		stdio: "inherit",
		env: { ...process.env, PYTHONIOENCODING: process.env.PYTHONIOENCODING || "utf-8" },
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
