# Releasing Harness

A release is one reviewed Git tag, one verified npm-format archive, one SPDX 2.3 software bill of materials, and checksums. GitHub Actions signs build-provenance and SBOM attestations with an ephemeral OIDC identity. Publishing to the npm registry remains separate so a GitHub release cannot consume registry credentials by accident.

## Before tagging

1. Update `CHANGELOG.md` and use the same base version in `package.json`, `.codex-plugin/plugin.json`, `.claude-plugin/plugin.json`, and `gemini-extension.json`.
2. Refresh the Codex cachebuster with the plugin-creator helper; do not append cachebuster suffixes by hand.
3. Run the release gates:

```bash
npm test
npm run pack:check
```

4. Commit and push `main`, then wait for the cross-platform `release-gate` workflow to pass.

## Create the release

Create and push an annotated tag that exactly matches `v` plus the package version:

```bash
git tag -a vX.Y.Z -m "Harness vX.Y.Z"
git push origin vX.Y.Z
```

The `publish-release-package` workflow repeats the deterministic gates, verifies the archive allowlist, installs the packed artifact in a clean directory, runs its portability check, creates an SPDX 2.3 SBOM plus `SHA256SUMS`, generates separate build-provenance and SBOM attestations, and publishes the three downloadable files to GitHub Releases. A mismatched tag, failed gate, missing file, unexpected private file, or duplicate release stops the workflow.

## Install a GitHub release archive

Download the `.tgz`, `harness.spdx.json`, and `SHA256SUMS` from the release. Verify both checksums and the signed attestations before installing:

```bash
sha256sum --check SHA256SUMS
gh attestation verify kingggg5-harness-X.Y.Z.tgz -R kingggg5/harness
gh attestation verify kingggg5-harness-X.Y.Z.tgz -R kingggg5/harness \
  --predicate-type https://spdx.dev/Document/v2.3
npm install --global ./kingggg5-harness-X.Y.Z.tgz
harness --help
```

The archive requires Node 18+ for the launcher and Python 3.12+ for Harness operations. An attestation proves which workflow and commit built the bytes; it is provenance evidence, not a claim that the software is vulnerability-free.
