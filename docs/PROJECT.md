# privacy-scan

<!-- created 2026-10-30 · board prefix TOOL-PSCAN (plan IDs TOOL-PRIVSCAN-*) · workspace tools -->

## Goal
Scans a project repo for leaks before it ships: private words (names of internal projects, hosts,
people, emails), secrets, and commit authors that are not allowed. What ships blocks; history only warns.

## Users
A developer who keeps private names out of what their projects publish.

## Scope
- In: `privacy-scan init` (dependency + config check), `privacy-scan init <repo>` (exceptions file),
  `privacy-scan <repo> [branch]` (scan), `--verify` (live-secret check), `install` / `uninstall`.
- Out (non-goals): cleaning history (that is a separate, gated rewrite), anything that needs a server.

## Depends on / used by
gitleaks (required); pre-commit, trufflehog, git-filter-repo (optional). Used by a release gate script.
