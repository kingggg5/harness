#!/usr/bin/env python3
"""Fail-closed static policy checks for Harness GitHub workflows."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_ROOT = ROOT / ".github" / "workflows"
PINNED_USE = re.compile(r"^\s*-\s+uses:\s+([^\s@]+)@([0-9a-f]{40})(?:\s+#.*)?$", re.MULTILINE)
ANY_USE = re.compile(r"^\s*-\s+uses:\s+([^\s@]+)@([^\s#]+)", re.MULTILINE)


def require(content: str, pattern: str, message: str, errors: list[str]) -> None:
	if re.search(pattern, content, re.MULTILINE) is None:
		errors.append(message)


def check_ci_covers_every_test_script(errors: list[str]) -> None:
	"""Keep ci.yml and the npm test chain from drifting apart.

	The CI workflow lists its steps explicitly so the memory-eval policy step can
	differ from ``npm test``. Every ``test:*`` script must therefore appear in the
	workflow, either as its underlying script path or as ``npm run <name>``.
	"""
	ci_path = WORKFLOW_ROOT / "ci.yml"
	if not ci_path.is_file():
		errors.append("ci.yml is missing")
		return
	ci = ci_path.read_text(encoding="utf-8")
	scripts = json.loads((ROOT / "package.json").read_text(encoding="utf-8")).get("scripts", {})
	for name, command in sorted(scripts.items()):
		if not name.startswith("test:") or not isinstance(command, str):
			continue
		script_paths = re.findall(r"(?:scripts|skills)/[A-Za-z0-9_./-]+\.(?:py|mjs|js)", command)
		if not script_paths:
			errors.append(f"package.json script {name} does not reference a test script file")
			continue
		if f"npm run {name}" in ci or all(path in ci for path in script_paths):
			continue
		errors.append(f"ci.yml does not run npm script {name} ({', '.join(script_paths)})")


def main() -> int:
	errors: list[str] = []
	check_ci_covers_every_test_script(errors)
	paths = sorted(WORKFLOW_ROOT.glob("*.yml")) + sorted(WORKFLOW_ROOT.glob("*.yaml"))
	if not paths:
		errors.append("no GitHub workflows found")
	for path in paths:
		content = path.read_text(encoding="utf-8")
		for match in ANY_USE.finditer(content):
			line = match.group(0)
			if PINNED_USE.fullmatch(line) is None:
				errors.append(f"{path.name}: action is not pinned to a 40-character commit: {line.strip()}")
		if "persist-credentials: true" in content:
			errors.append(f"{path.name}: checkout credentials must not persist")
		if re.search(r"^\s*pull_request_target\s*:", content, re.MULTILINE):
			errors.append(f"{path.name}: pull_request_target is prohibited")

	release = (WORKFLOW_ROOT / "release.yml").read_text(encoding="utf-8")
	require(release, r"^\s+id-token:\s+write\s*$", "release workflow must grant id-token: write", errors)
	require(release, r"^\s+attestations:\s+write\s*$", "release workflow must grant attestations: write", errors)
	require(release, r"^\s+artifact-metadata:\s+write\s*$", "release workflow must grant artifact-metadata: write", errors)
	require(release, r"uses:\s+actions/attest@[0-9a-f]{40}", "release workflow must use a commit-pinned actions/attest", errors)
	require(release, r"npm run sbom:generate", "release workflow must generate an SBOM", errors)
	require(release, r"bin/harness\.js portability --json", "release workflow must run the installed package portability gate", errors)
	require(release, r"sbom-path:\s+dist/harness\.spdx\.json", "release workflow must attest the SPDX SBOM", errors)
	require(release, r"sha256sum \*\.tgz \*\.spdx\.json", "release checksums must cover archive and SBOM", errors)
	require(release, r"gh release create", "release workflow must publish through GitHub Releases", errors)
	if errors:
		for error in errors:
			print(f"[FAIL] {error}")
		return 1
	print(f"Workflow policy passed: {len(paths)} workflows; actions commit-pinned; CI covers every npm test script; release SBOM and attestations enforced.")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
