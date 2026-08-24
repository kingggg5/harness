# Releasing Harness

A release is one reviewed Git tag, one verified npm-format archive, and one checksum file. Publishing to the npm registry is deliberately separate so a GitHub release cannot consume registry credentials by accident.

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
git tag -a v0.4.0 -m "Harness v0.4.0"
git push origin v0.4.0
```

The `publish-release-package` workflow repeats the deterministic gates, verifies the archive allowlist, installs the packed artifact in a clean directory, checks the CLI entry point, creates `SHA256SUMS`, and publishes both files to GitHub Releases. A mismatched tag, failed gate, missing file, unexpected private file, or duplicate release stops the workflow.

## Install a GitHub release archive

Download the `.tgz` and `SHA256SUMS` from the release, verify the checksum, then install:

```bash
npm install --global ./kingggg5-harness-0.4.0.tgz
harness --help
```

The archive requires Node 18+ for the launcher and Python 3.12+ for Harness operations.
