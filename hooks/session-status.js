#!/usr/bin/env node
// Claude Code SessionStart hook: surface the current Harness run in one line.
//
// Prints nothing when the working directory has no .harness/ project so the
// plugin stays silent everywhere else. It reads only STATE.json, IDENTITY.json,
// and MEMORY.json's revision; it never runs Python or mutates anything.

"use strict";

const fs = require("node:fs");
const path = require("node:path");

function readStdin() {
	return new Promise((resolve) => {
		const chunks = [];
		process.stdin.on("data", (chunk) => chunks.push(chunk));
		process.stdin.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
		process.stdin.on("error", () => resolve(""));
	});
}

function readJson(file) {
	const data = fs.readFileSync(file, "utf8");
	if (data.length > 1024 * 1024) throw new Error("file too large");
	return JSON.parse(data);
}

function clip(value, max) {
	const text = String(value ?? "").replace(/\s+/g, " ").trim();
	return text.length > max ? text.slice(0, max - 1) + "…" : text;
}

async function main() {
	let cwd = process.cwd();
	try {
		const payload = JSON.parse(await readStdin());
		if (payload && typeof payload.cwd === "string" && payload.cwd) cwd = payload.cwd;
	} catch {
		// Fall back to the process working directory.
	}
	const harness = path.join(cwd, ".harness");
	const statePath = path.join(harness, "STATE.json");
	if (!fs.existsSync(statePath)) return 0;
	try {
		const state = readJson(statePath);
		let projectId = "";
		let revision = "";
		try { projectId = String(readJson(path.join(harness, "IDENTITY.json")).project_id || ""); } catch {}
		try { revision = String(readJson(path.join(harness, "MEMORY.json")).revision ?? ""); } catch {}
		const runId = clip(state.run_id, 48) || "none";
		const lines = [
			`Harness project detected in ${cwd}: project ${clip(projectId, 48) || "unknown"}, run ${runId}, state ${clip(state.state, 24) || "unknown"}, memory revision ${revision || "unknown"}.`,
			state.next_action ? `Recorded next action: ${clip(state.next_action, 200)}` : "No next action is recorded.",
			"Use `Harness resume` to continue the recorded run, `Harness: <task>` to start new work, or `harness doctor --project .` for a health report. Canonical memory changes go through memory_ops.py, not direct edits.",
		];
		process.stdout.write(lines.join("\n") + "\n");
	} catch {
		// A damaged state file is reported by `harness doctor`, not by this hook.
	}
	return 0;
}

main().then((code) => process.exit(code), () => process.exit(0));
