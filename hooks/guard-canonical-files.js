#!/usr/bin/env node
// Claude Code PreToolUse hook: refuse direct edits to canonical Harness files.
//
// Harness policy says the Project Manager writes durable memory only through
// memory_ops.py, never by hand-editing MEMORY.json, and never touches the
// pinned runtime, generated views, identity, or ledgers. This hook turns that
// policy into a mechanical refusal for Edit/Write-style tools. It is a guard
// rail, not the security boundary: the deterministic core still validates
// every canonical file on its own. A malformed hook payload therefore fails
// open rather than blocking unrelated work.

"use strict";

const GUARDED = [
	{ pattern: /(^|[\\/])\.harness[\\/]MEMORY\.json$/i, why: "MEMORY.json is canonical memory; use `harness remember|correct|forget|close-run` (memory_ops.py) so revisions, validation, and tombstones stay intact." },
	{ pattern: /(^|[\\/])\.harness[\\/]IDENTITY\.json$/i, why: "IDENTITY.json binds the project; use `init_project.py --rebind-identity --dry-run` and approve its digest instead of editing it." },
	{ pattern: /(^|[\\/])\.harness[\\/](CONTEXT|PREFERENCES|DECISIONS)\.md$/i, why: "This file is a generated view of MEMORY.json; change the record with memory_ops.py and rerun `harness render`." },
	{ pattern: /(^|[\\/])\.harness[\\/]runtime[\\/]/i, why: "The pinned runtime is digest-checked; use `upgrade_project.py --dry-run` and approve its digest instead of editing pinned files." },
	{ pattern: /(^|[\\/])\.harness[\\/](runtime-history|runtime-recovery|migrations)[\\/]/i, why: "Runtime history, recovery, and migration archives are evidence; never edit them by hand." },
	{ pattern: /(^|[\\/])\.harness[\\/]\.cache[\\/]/i, why: "Ledgers and traces under .harness/.cache are receipts; edit nothing there. Use graph-run, loop-run, run-approve, or run-cancel commands." },
];

function readStdin() {
	return new Promise((resolve) => {
		const chunks = [];
		process.stdin.on("data", (chunk) => chunks.push(chunk));
		process.stdin.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
		process.stdin.on("error", () => resolve(""));
	});
}

function deny(reason) {
	process.stdout.write(JSON.stringify({
		hookSpecificOutput: {
			hookEventName: "PreToolUse",
			permissionDecision: "deny",
			permissionDecisionReason: `Harness: ${reason}`,
		},
	}) + "\n");
}

async function main() {
	let payload;
	try {
		payload = JSON.parse(await readStdin());
	} catch {
		return 0;
	}
	const input = payload && typeof payload.tool_input === "object" && payload.tool_input ? payload.tool_input : {};
	const target = typeof input.file_path === "string" ? input.file_path : (typeof input.notebook_path === "string" ? input.notebook_path : "");
	if (!target) return 0;
	for (const rule of GUARDED) {
		if (rule.pattern.test(target)) {
			deny(rule.why);
			return 0;
		}
	}
	return 0;
}

main().then((code) => process.exit(code), () => process.exit(0));
