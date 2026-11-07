# privacy-scan

<!-- created 2026-10-30 · board prefix TOOL-PSCAN (plan IDs TOOL-PRIVSCAN-*) · workspace tools -->

## Goal
Pre-release Git leak scanner CLI (Gitleaks + TruffleHog): block private words, secrets, and unauthorized emails in code & build output.

## Users
A developer who keeps private names out of what their projects publish.

## Scope
- In: `privacy-scan init` (dependency + config check), `privacy-scan init <repo>` (exceptions file),
  `privacy-scan <repo> [branch]` (scan), `--verify` (live-secret check), `install` / `uninstall`.
- Out (non-goals): cleaning history (that is a separate, gated rewrite), anything that needs a server.

## Depends on / used by
gitleaks (required); pre-commit, trufflehog, git-filter-repo (optional). Used by a release gate script.
