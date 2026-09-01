#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import { statSync } from "node:fs";
import { dirname, isAbsolute, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const launcher = join(root, "bin", "harness.js");

function assert(condition, message) {
	if (!condition) throw new Error(message);
}

function installedPython() {
	for (const candidate of ["python3", "python", "py"]) {
		const probe = spawnSync(candidate, ["-B", "-c", "import os, sys; print(os.path.realpath(sys.executable))"], {
			cwd: root,
			encoding: "utf8",
			env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1", PYTHONIOENCODING: "utf-8" },
			timeout: 5000,
			windowsHide: true,
		});
		const value = probe.stdout.trim();
		if (probe.status === 0 && isAbsolute(value)) {
			try {
				if (statSync(value).isFile()) return value;
			} catch {
				// Try the next known launcher.
			}
		}
	}
	throw new Error("Python 3.12+ is required for launcher tests");
}

try {
	const python = installedPython();
	const pathName = Object.keys(process.env).find((name) => name.toUpperCase() === "PATH") || "PATH";
	const pinned = spawnSync(process.execPath, [launcher, "portability", "--json"], {
		cwd: root,
		encoding: "utf8",
		env: { ...process.env, HARNESS_PYTHON: python, [pathName]: "" },
		timeout: 30000,
		windowsHide: true,
	});
	assert(pinned.status === 0, pinned.stderr || `absolute HARNESS_PYTHON launch exited ${pinned.status}`);
	const report = JSON.parse(pinned.stdout);
	assert(report.ok === true, "absolute HARNESS_PYTHON did not run the expected package command");

	const rejected = spawnSync(process.execPath, [launcher, "portability", "--json"], {
		cwd: root,
		encoding: "utf8",
		env: { ...process.env, HARNESS_PYTHON: "python" },
		timeout: 10000,
		windowsHide: true,
	});
	assert(rejected.status !== 0 && rejected.stderr.includes("HARNESS_PYTHON must be an absolute"), "relative HARNESS_PYTHON must fail closed");
	console.log("Launcher tests passed: canonical absolute interpreter required and honored.");
} catch (error) {
	console.error(`Launcher tests failed: ${error.message}`);
	process.exit(1);
}
