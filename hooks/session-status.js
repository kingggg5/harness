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

// Active project decisions and preferences let every session follow recorded
// project rules without first searching .harness/; bounded so it stays cheap.
const DIGEST_RECORDS = 8;
const DIGEST_VALUE_CHARS = 220;
const DIGEST_TOTAL_CHARS = 1600;

function decisionDigest(memory) {
	const records = Array.isArray(memory?.records) ? memory.records : [];
	const active = records
		.filter((r) => r && r.status === "Active" && r.scope === "project" && (r.kind === "decision" || r.kind === "preference"))
		.sort((a, b) => (a.kind === b.kind ? String(b.updated_at || "").localeCompare(String(a.updated_at || "")) : a.kind === "decision" ? -1 : 1));
	if (!active.length) return [];
	const out = ["Recorded project decisions and preferences (.harness/MEMORY.json); follow them unless the user changes one:"];
	let used = out[0].length;
	let shown = 0;
	for (const record of active.slice(0, DIGEST_RECORDS)) {
		const line = `- [${record.kind}] ${clip(record.key, 60)}: ${clip(record.value, DIGEST_VALUE_CHARS)}`;
		if (used + line.length > DIGEST_TOTAL_CHARS) break;
		out.push(line);
		used += line.length;
		shown += 1;
	}
	if (shown < active.length) out.push(`(${active.length - shown} more in .harness/DECISIONS.md and PREFERENCES.md)`);
	return out;
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
		let memory = null;
		try { projectId = String(readJson(path.join(harness, "IDENTITY.json")).project_id || ""); } catch {}
		try { memory = readJson(path.join(harness, "MEMORY.json")); revision = String(memory.revision ?? ""); } catch {}
		const runId = clip(state.run_id, 48) || "none";
		const lines = [
			`Harness project detected in ${cwd}: project ${clip(projectId, 48) || "unknown"}, run ${runId}, state ${clip(state.state, 24) || "unknown"}, memory revision ${revision || "unknown"}.`,
			state.next_action ? `Recorded next action: ${clip(state.next_action, 200)}` : "No next action is recorded.",
			"Use `Harness resume` to continue the recorded run, `Harness: <task>` to start new work, or `harness doctor --project .` for a health report. Canonical memory changes go through memory_ops.py, not direct edits.",
		];
		lines.push(...decisionDigest(memory));
		process.stdout.write(lines.join("\n") + "\n");
	} catch {
		// A damaged state file is reported by `harness doctor`, not by this hook.
	}
	return 0;
}

main().then((code) => process.exit(code), () => process.exit(0));
