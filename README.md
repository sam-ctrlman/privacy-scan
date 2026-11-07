# privacy-scan

**Pre-release Git repository leak scanner CLI and Claude Code skill powered by Gitleaks and TruffleHog — blocks private words, secrets, and unauthorized emails in shipping branches and build output while auditing git history.**

Standard secret scanners look for API keys and tokens, but internal codenames, private hostnames, employee names, and personal email addresses can still slip into public releases or bundled client assets (`.next/static`, `.next/server/app`). `privacy-scan` combines Gitleaks custom `private-word` rules, email allowlisting, `.release-exclude` release simulation, and optional TruffleHog live-secret verification into a single pre-release gate where **what ships blocks (`exit 1`)** and **historical commits warn**.

---

## Why Use `privacy-scan`?

- **Two-Tier Release Gate (`ships` vs. `history`):** Files that actually ship in your release branch and local build output (`public/`, `.next/static`, `.next/server/app`) **block** on any leak (`exit 1`), while findings in old commits **warn** without breaking builds unnecessarily.
- **Release Preview Simulation (`.release-exclude`):** When scanning a non-`production` branch (such as `main` or `feat/*`), `privacy-scan` automatically strips paths listed in `.release-exclude` inside a temporary archive so you test the exact tree a production release would ship.
- **Scoped Per-Repo Allowlists (`.privacy-allow`):** Allow a project's own public brand name repo-wide (`word: my-brand`), restrict an internal term to specific files (`word: build-host in: deploy/*.cjs`), or allow specific author/contact email patterns (`email: *@example.com`).
- **Zero Silent Suppression (`allowed=N` & `--allowed`):** Every match hidden by `.privacy-allow` is still counted in the summary line (`allowed=N (M entries)`), and `--allowed` prints the exact `file:line` (and `@commit` in history) where each exception matched.
- **Safe Default Output:** Prints aggregate counts only by default so running a scan in CI or a shared terminal never echoes matched private words or secrets to `stdout` (pass `--detail` only when you explicitly want to inspect matched strings).
- **Live Secret Verification (`--verify`):** Optionally invokes `trufflehog --only-verified` whenever a secret rule triggers to check whether the credential is still active.

---

## Example Output

```text
$ privacy-scan ~/projects/my-web-app main
[notice] main is not production — left out 14 file(s) on .release-exclude
[info] my-web-app @ main  (allow: 2 word(s), 4 email pattern(s))
[ok]     ships    clean private-words=0 secrets=0 emails=0  allowed=6 (2 entries)
[notice] history  warn  private-words=2 secrets=0 emails=1  allowed=19 (3 entries)
[ok] my-web-app: what ships is clean (history has warnings)
```

Auditing where `.privacy-allow` hid matches (`--allowed`):
```text
$ privacy-scan ~/projects/my-web-app main --allowed
...
[allowed]   ships word my-brand  ×5 in 2 file(s)
[allowed]       src/app/layout.tsx  ×3  line 12, 28, 44
[allowed]       README.md  ×2  line 1, 19
[allowed]   ships email support@example.com  ×1 in 1 file(s)
[allowed]       src/components/Footer.tsx  ×1  line 31
```

---

## Installation

```sh
git clone <remote-url> ~/tools/projects/privacy-scan
python3 ~/tools/projects/privacy-scan/bin/privacy-scan.py install
privacy-scan init          # verify dependencies + ~/.config/gitleaks/private.toml
```

Once installed:
1. Run `privacy-scan` from **any terminal shell**.
2. Run `/privacy-scan` directly **inside Claude Code**.

To remove the symlinks:
```sh
privacy-scan uninstall
```

---

## Dependencies & Private-Word Config

| Package | Required? | Role |
| :--- | :---: | :--- |
| **`gitleaks`** | **Required** | Core scan engine for secrets + custom `private-word` regex rule |
| **`pre-commit`** | Optional | Per-repository pre-commit hook management |
| **`trufflehog`** | Optional | `--verify` flag: checks whether a detected secret is live |
| **`git-filter-repo`** | Optional | History scrubbing (used only behind a dedicated manual gate) |

`privacy-scan init` checks all 4 tools and prints the exact package-manager command (`pacman` / AUR, `apt`, or `brew`) for anything missing. It never executes `sudo` on its own.

### External Private-Word Configuration (`private.toml`)
Keep your private word list **outside** every git repository in `~/.config/gitleaks/private.toml` (`chmod 600`, or override with `$PRIVACY_SCAN_CONFIG`):

```toml
[extend]
useDefault = true

[[rules]]
id = "private-word"
description = "Internal hostnames, codenames, and private identifiers"
regex = '''(?i)(internal-codename|private-host-01|secret-client)'''
```

---

## Commands & Options

| Command / Option | Description |
| :--- | :--- |
| `privacy-scan init` | Verify required/optional dependencies, `~/.config/gitleaks/private.toml` (`private-word` rule + file permissions), and global `core.hooksPath` pre-commit hook. |
| `privacy-scan init <repo>` | Run `init` checks, create `<repo>/.privacy-allow` (seeded with the repo's local `user.email`), and append `.privacy-allow` to `<repo>/.release-exclude`. |
| `privacy-scan <repo> [branch]` | Scan `<repo>` on `[branch]` (defaults to `production` if present, otherwise `main`). |
| `--verify` | Run `trufflehog --only-verified` when Gitleaks reports a secret finding. |
| `--detail` | Print per-word and per-email match counts (**warning:** prints matched private text to stdout). |
| `--allowed` | Print every `file:line` (and `@commit` in history) where `.privacy-allow` suppressed a match. |
| `privacy-scan install` / `uninstall` | Create or remove `~/.local/bin/privacy-scan` and `~/.claude/skills/privacy-scan` symlinks. |

---

## Configuring `.privacy-allow`

Place `.privacy-allow` at the root of a repository (and list `.privacy-allow` in `.release-exclude` so the exception list itself never ships):

```text
# Project's public brand name — allowed across the entire repo
word: my-brand

# Internal word allowed ONLY in specific file globs (blocks everywhere else)
word: build-host  in: deploy/*.cjs, scripts/build-*.sh

# Allowed author or contact email addresses (fnmatch wildcards supported)
email: user@example.com
email: *@example.com
```

- **Built-in Email Allowances:** GitHub noreply addresses (`*@users.noreply.github.com`, `noreply@github.com`) and the repository's local `git config --local user.email` are automatically allowed.
- **Asset Filename Filtering:** Strings like `logo@2x.png` or `pkg@1.2.3/index.js` are automatically recognized as asset/package paths rather than email addresses.

---

## Exit Codes & Project Layout

### Exit Codes
- `0` — Clean (`ships` has zero findings; `history` warnings and `allowed` matches are permitted).
- `1` — Blocking leak found in `ships` (branch files or build output).
- `2` — Usage error (invalid arguments, non-git path, or missing branch).
- `4` — `~/.config/gitleaks/private.toml` missing or lacks the `private-word` rule.
- `5` — `gitleaks` binary not installed.
- `130` — Interrupted by user (`Ctrl-C`).

### Directory Structure
```text
~/tools/projects/privacy-scan/
├── .privacy-allow
├── LICENSE
├── README.md
├── bin/privacy-scan.py           # CLI executable & Gitleaks/TruffleHog orchestrator
├── docs/
│   ├── PROJECT.md
│   └── STATUS.md
└── skills/privacy-scan/SKILL.md  # Claude Code /privacy-scan skill definition
```

---

## Frequently Asked Questions (FAQ)

**Why keep `private.toml` outside the repository instead of in `.gitleaks.toml`?**  
A repository-tracked `.gitleaks.toml` would expose the very list of private codenames, hostnames, and client names you are trying to keep out of public commits. Keeping `~/.config/gitleaks/private.toml` outside all repos (`chmod 600`) lets you scan every project against your private word list without leaking the list itself.

**Why does `ships` block while `history` only warns?**  
Rewriting git history (`git filter-repo` + force-push) is destructive and breaks existing clones. For repositories with a `production` release branch, blocking on `ships` guarantees nothing private ever reaches production or compiled client bundles (`.next/static`), while `history` warnings inform you if an older dev commit needs a gated scrub before making the entire repository history public.

**Does `privacy-scan` print secrets or private words to the terminal?**  
No. By default, `privacy-scan` keeps matched strings in memory only to evaluate `.privacy-allow` rules and prints strictly numeric counts (`private-words=0 secrets=0 emails=0`). Matched text is only printed if you explicitly pass `--detail` or `--allowed`.
