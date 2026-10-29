---
description: Scan a project repo for leaks (private words, secrets, foreign emails) before it ships
argument-hint: "[init [repo] | <repo> [branch] [--verify] [--detail] [--allowed] | install | uninstall]"
---

Run `privacy-scan $ARGUMENTS` from the user's current directory using the Bash tool.

`privacy-scan` is a Python tool at `~/tools/projects/privacy-scan/bin/privacy-scan.py` (symlinked to `~/.local/bin/privacy-scan`). This slash command file is at `~/tools/projects/privacy-scan/commands/privacy-scan.md` (symlinked to `~/.claude/commands/privacy-scan.md`).

Actions:

- **`privacy-scan init`**: check the 4 dependencies (gitleaks required; pre-commit, trufflehog, git-filter-repo optional) and the private-word config. Prints install commands for anything missing; it never runs sudo. Run this before first use. A scan refuses while init would fail.
- **`privacy-scan init <repo>`**: same, then write `<repo>/.privacy-allow` (the repo's exceptions) and add it to `.release-exclude`. This edits files in the repo, so in a gated workspace it needs a runbook step first.
- **`privacy-scan <repo> [branch]`**: scan. `ships` (branch files + build output) BLOCKS on findings (exit 1); `history` only warns. Read-only.
- **`--verify`**: also ask trufflehog whether a found secret is still live.
- **`--detail`**: list each matched word / email. This prints private text, so only use it when the user asks.
- **`--allowed`**: list where `.privacy-allow` hid a match (entry → file:line). Entries can be scoped: `word: X  in: <glob>, …`.
- **`privacy-scan install` / `uninstall`**: manage both symlinks. Idempotent.

After it returns, surface the `[ok]` / `[error]` / `[notice]` / `[install]` log lines to the user. Do NOT improvise steps the tool does not perform, and never run the printed `sudo` install lines yourself: the user types them.

Pass through `$ARGUMENTS` verbatim.
