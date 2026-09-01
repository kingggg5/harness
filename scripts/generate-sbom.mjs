#!/usr/bin/env node

import { createHash } from "node:crypto";
import { existsSync, lstatSync, readFileSync, writeFileSync } from "node:fs";
import { basename, dirname, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const MAX_FILES = 2000;
const MAX_FILE_BYTES = 8 * 1024 * 1024;
const MAX_ARCHIVE_BYTES = 64 * 1024 * 1024;

function fail(message) {
	throw new Error(message);
}

function parseArgs(argv) {
	const args = {};
	for (let index = 0; index < argv.length; index += 2) {
		const key = argv[index];
		const value = argv[index + 1];
		if (!key?.startsWith("--") || value === undefined) fail(`invalid argument near ${key ?? "end"}`);
		args[key.slice(2)] = value;
	}
	if (!args.archive || !args.output) fail("--archive and --output are required");
	return args;
}

function hash(algorithm, bytes) {
	return createHash(algorithm).update(bytes).digest("hex");
}

function normalizedRelative(path) {
	const absolute = resolve(path);
	const item = relative(REPO_ROOT, absolute).split(sep).join("/");
	if (!item || item === ".." || item.startsWith("../")) fail(`package file escapes repository: ${path}`);
	return item;
}

function readRegularFile(path, label, maximum) {
	let metadata;
	try {
		metadata = lstatSync(path);
	} catch (error) {
		fail(`${label} cannot be inspected: ${error.message}`);
	}
	if (!metadata.isFile() || metadata.isSymbolicLink() || metadata.nlink > 1) {
		fail(`${label} must be one regular non-linked file: ${path}`);
	}
	if (metadata.size <= 0) fail(`${label} must not be empty: ${path}`);
	if (metadata.size > maximum) fail(`${label} exceeds ${maximum} bytes: ${path}`);
	try {
		return readFileSync(path);
	} catch (error) {
		fail(`${label} cannot be read: ${error.message}`);
	}
}

function packageFiles() {
	const npmCli = process.env.npm_execpath;
	if (!npmCli) fail("npm CLI path is unavailable; invoke through npm run sbom:generate");
	const result = spawnSync(process.execPath, [npmCli, "pack", "--dry-run", "--json", "--ignore-scripts"], {
		cwd: REPO_ROOT,
		encoding: "utf8",
		windowsHide: true,
		maxBuffer: 4 * 1024 * 1024,
	});
	if (result.error) fail(`npm pack failed: ${result.error.message}`);
	if (result.status !== 0) fail(result.stderr.trim() || `npm pack exited ${result.status}`);
	let report;
	try {
		[report] = JSON.parse(result.stdout);
	} catch (error) {
		fail(`npm pack returned invalid JSON: ${error.message}`);
	}
	if (!Array.isArray(report?.files) || report.files.length === 0 || report.files.length > MAX_FILES) {
		fail(`npm pack file count must be between 1 and ${MAX_FILES}`);
	}
	return report.files.map((entry) => entry.path.replaceAll("\\", "/")).sort();
}

function createdAt(explicit) {
	if (explicit) {
		const parsed = new Date(explicit);
		if (Number.isNaN(parsed.valueOf())) fail("--created must be an ISO-8601 timestamp");
		return parsed.toISOString().replace(".000Z", "Z");
	}
	if (process.env.SOURCE_DATE_EPOCH) {
		const seconds = Number.parseInt(process.env.SOURCE_DATE_EPOCH, 10);
		if (!Number.isSafeInteger(seconds) || seconds < 0) fail("SOURCE_DATE_EPOCH must be a non-negative integer");
		return new Date(seconds * 1000).toISOString().replace(".000Z", "Z");
	}
	return new Date().toISOString().replace(".000Z", "Z");
}

function main() {
	const args = parseArgs(process.argv.slice(2));
	const archivePath = resolve(args.archive);
	const outputPath = resolve(args.output);
	if (!existsSync(archivePath)) fail(`archive does not exist: ${archivePath}`);
	if (existsSync(outputPath)) fail(`refusing to overwrite existing output: ${outputPath}`);
	const manifest = JSON.parse(readFileSync(resolve(REPO_ROOT, "package.json"), "utf8"));
	const archiveBytes = readRegularFile(archivePath, "archive", MAX_ARCHIVE_BYTES);
	const archiveSha256 = hash("sha256", archiveBytes);
	const files = [];
	const verificationHashes = [];
	for (const packagePath of packageFiles()) {
		const sourcePath = resolve(REPO_ROOT, packagePath);
		normalizedRelative(sourcePath);
		const bytes = readRegularFile(sourcePath, `package file ${packagePath}`, MAX_FILE_BYTES);
		const sha256 = hash("sha256", bytes);
		verificationHashes.push(hash("sha1", bytes));
		files.push({
			SPDXID: `SPDXRef-File-${hash("sha256", Buffer.from(packagePath)).slice(0, 20)}`,
			fileName: `./${packagePath}`,
			checksums: [{ algorithm: "SHA256", checksumValue: sha256 }],
			licenseConcluded: "NOASSERTION",
			copyrightText: "NOASSERTION",
		});
	}
	const packageVerificationCode = hash("sha1", Buffer.from(verificationHashes.sort().join("")));
	const packageId = "SPDXRef-Package-Harness";
	const documentId = "SPDXRef-DOCUMENT";
	const repository = manifest.repository?.url?.replace(/^git\+/, "") ?? "https://github.com/kingggg5/harness";
	const purlName = manifest.name.startsWith("@") ? `%40${manifest.name.slice(1)}` : manifest.name;
	const relationships = [
		{ spdxElementId: documentId, relationshipType: "DESCRIBES", relatedSpdxElement: packageId },
		...files.map((file) => ({
			spdxElementId: packageId,
			relationshipType: "CONTAINS",
			relatedSpdxElement: file.SPDXID,
		})),
	];
	const sbom = {
		spdxVersion: "SPDX-2.3",
		dataLicense: "CC0-1.0",
		SPDXID: documentId,
		name: `${manifest.name}-${manifest.version}`,
		documentNamespace: `${repository.replace(/\.git$/, "")}/spdx/${manifest.version}/${archiveSha256}`,
		creationInfo: {
			created: createdAt(args.created),
			creators: [`Tool: ${manifest.name}-generate-sbom/${manifest.version}`],
		},
		packages: [{
			name: manifest.name,
			SPDXID: packageId,
			versionInfo: manifest.version,
			packageFileName: basename(archivePath),
			downloadLocation: "NOASSERTION",
			filesAnalyzed: true,
			packageVerificationCode: { packageVerificationCodeValue: packageVerificationCode },
			checksums: [{ algorithm: "SHA256", checksumValue: archiveSha256 }],
			licenseConcluded: manifest.license ?? "NOASSERTION",
			licenseDeclared: manifest.license ?? "NOASSERTION",
			copyrightText: "NOASSERTION",
			externalRefs: [{
				referenceCategory: "PACKAGE-MANAGER",
				referenceType: "purl",
				referenceLocator: `pkg:npm/${purlName}@${manifest.version}`,
			}],
		}],
		files,
		relationships,
	};
	writeFileSync(outputPath, `${JSON.stringify(sbom, null, 2)}\n`, { encoding: "utf8", flag: "wx" });
	console.log(`SPDX SBOM written: ${outputPath}; ${files.length} files; archive sha256 ${archiveSha256}`);
}

try {
	main();
} catch (error) {
	console.error(`SBOM generation failed: ${error.message}`);
	process.exit(1);
}
