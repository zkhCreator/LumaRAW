# Publishing the Source

Publish a checked source snapshot, not an entire development workspace. Original code uses MIT; preserve `LICENSE`, `THIRD_PARTY_NOTICES.md`, and all upstream attribution under `licenses/`. Old app bundles, archives, raw logs, and local catalogs are outside this publication boundary.

```sh
# A clean source snapshot
python3 scripts/check_public.py --strict
# A development checkout may contain ignored local build artifacts
python3 scripts/check_public.py
python3 scripts/package_public.py /absolute/new-source.zip
```

The packager includes only approved source, documentation, dependency locks, icons, and ICC assets. Unknown files, symlinks, and credential-looking entries are rejected. The scanner checks machine home paths, local task links, common token patterns, private-key blocks, and credential-bearing URLs. Findings contain categories and relative paths, never matched values. PNG text and EXIF metadata are disallowed, including PNG images embedded in ICNS containers.

RAW build inputs under `scripts/rawpy-wheel/` have an exact allowlist for the
three reviewed patches, toolchain and dependency input/lock files. The exception
does not allow arbitrary patches, archives or wheels. Upstream codec attribution
remains under `licenses/raw-codecs/`; all downloaded and generated build/runtime
artifacts stay outside the source snapshot.

Generated libraries, apps, photos, databases, logs, test receipts, environments, and caches are excluded. First-party project text is English; upstream attribution and user data are not rewritten.

When the root is a Git repository, the scanner also rejects forbidden entries in the index, including force-added ignored files. It does **not** inspect or rewrite Git history. `.gitignore` cannot remove earlier commits. Start from the clean snapshot instead of attaching private history. The tools never initialize, commit, push, or change remote visibility.

Pattern checks do not prove the absence of every unknown secret or personal detail, and they are not a copyright audit. Credential-looking entries are rejected before opening; any real credential must be handled manually by its owner. Upstream author names and contact information are preserved as attribution. Review new files and assets before publication.

Runtime catalogs contain original photo paths. Probe output may contain local paths and EXIF. Keep those files local. The MCP example uses `/Applications/LumaRAW.app`; do not replace it with a private machine configuration in the repository.

Public application binaries require a separate privacy and dependency-license review, signing, and notarization. A source scan does not clear previously built application packages.

## GitHub Releases

Pushing a stable version tag such as `v0.4.1` runs `.github/workflows/release.yml`.
The workflow requires a matching version in `pyproject.toml` and reviewed English
notes in `.github/release-notes/<tag>.md`. It packages the checked source, verifies
archive contents, and publishes the source ZIP, per-file manifest, and SHA-256
checksums. It never uploads local application bundles or photo libraries.

The official checkout action is pinned to a commit and does not persist checkout
credentials. Publication uses GitHub's temporary repository token, scoped to the
release job; no personal token or signing key is needed. The workflow does not
overwrite an existing release. Inspect a failed run before retrying if a release
was partially created.

To prepare the same assets locally from a clean source directory:

```sh
python3 -B scripts/prepare_release.py --tag v0.4.1 --output /absolute/new-release-directory
```
