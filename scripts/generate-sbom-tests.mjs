#!/usr/bin/env node

import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const temp = mkdtempSync(join(tmpdir(), "harness-sbom-"));

function assert(condition, message) {
	if (!condition) throw new Error(message);
}

try {
	const archive = join(temp, "harness-test.tgz");
	const output = join(temp, "harness.spdx.json");
	writeFileSync(archive, "deterministic test archive", "utf8");
	const result = spawnSync(process.execPath, [
		join(root, "scripts", "generate-sbom.mjs"),
		"--archive", archive,
		"--output", output,
		"--created", "2026-09-01T00:00:00Z",
	], {
		cwd: root,
		encoding: "utf8",
		env: { ...process.env },
		windowsHide: true,
	});
	assert(result.status === 0, result.stderr || `generator exited ${result.status}`);
	const sbom = JSON.parse(readFileSync(output, "utf8"));
	const manifest = JSON.parse(readFileSync(join(root, "package.json"), "utf8"));
	assert(sbom.spdxVersion === "SPDX-2.3", "SPDX version mismatch");
	assert(sbom.creationInfo.created === "2026-09-01T00:00:00Z", "created timestamp mismatch");
	assert(sbom.packages?.[0]?.name === manifest.name, "package name mismatch");
	assert(sbom.packages?.[0]?.versionInfo === manifest.version, "package version mismatch");
	assert(Array.isArray(sbom.files) && sbom.files.length > 20, "packaged file inventory is unexpectedly small");
	assert(sbom.files.every((file) => file.fileName.startsWith("./") && file.checksums?.[0]?.algorithm === "SHA256"), "file checksum contract failed");
	assert(sbom.relationships.length === sbom.files.length + 1, "relationship count mismatch");
	const overwrite = spawnSync(process.execPath, [
		join(root, "scripts", "generate-sbom.mjs"),
		"--archive", archive,
		"--output", output,
		"--created", "2026-09-01T00:00:00Z",
	], {
		cwd: root,
		encoding: "utf8",
		env: { ...process.env },
		windowsHide: true,
	});
	assert(overwrite.status !== 0 && overwrite.stderr.includes("refusing to overwrite existing output"), "generator must refuse overwriting an existing SBOM");
	console.log(`SBOM tests passed: ${sbom.files.length} packaged files described.`);
} finally {
	rmSync(temp, { recursive: true, force: true });
}
