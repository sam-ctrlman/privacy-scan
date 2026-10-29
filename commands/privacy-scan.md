---
description: "TODO: privacy-scan — describe what this slash command does"
argument-hint: "[run|install|uninstall]"
---

Run `privacy-scan $ARGUMENTS` from the user's current directory using the Bash tool.

`privacy-scan` is a Python tool at `~/tools/projects/privacy-scan/bin/privacy-scan.py` (symlinked to `~/.local/bin/privacy-scan`). This slash command file is at `~/tools/projects/privacy-scan/commands/privacy-scan.md` (symlinked to `~/.claude/commands/privacy-scan.md`).

Actions:

- **`privacy-scan`** or **`privacy-scan run`** — TODO: the workflow this tool automates (not implemented yet — edit `cmd_run()` in the script).
- **`privacy-scan install`** — create both symlinks (bin + Claude command). Idempotent.
- **`privacy-scan uninstall`** — remove both symlinks. Idempotent.

After it returns, surface the `[ok]` / `[error]` / `[notice]` log lines to the user. Do NOT improvise steps the tool does not perform — the tool owns its workflow.

Pass through `$ARGUMENTS` verbatim. Valid args: `run`, `install`, `uninstall`, or empty (defaults to `run`).
