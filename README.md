# privacy-scan

Scan a project repo for leaks before it ships: private words (internal project, host and people names),
secrets, and email addresses that aren't on the repo's allow list.

## Install

```sh
git clone <remote-url> ~/tools/projects/privacy-scan
python3 ~/tools/projects/privacy-scan/bin/privacy-scan.py install
privacy-scan init          # check dependencies + config before first use
```

After install, `privacy-scan` works in any shell and `/privacy-scan` works in Claude Code.

## Dependencies

| Package | Needed | Role |
|---|---|---|
| gitleaks | required | scan engine: private words + secrets |
| pre-commit | optional | per-repo hook chain |
| trufflehog | optional | `--verify`: is a found secret still live |
| git-filter-repo | optional | history rewrite, only behind its own gate |

`privacy-scan init` prints the install command for whatever is missing (pacman / AUR, apt, brew). It never runs sudo.

The private words come from the `private-word` rule in a gitleaks config kept outside every repo
(default `~/.config/gitleaks/private.toml`, override with `PRIVACY_SCAN_CONFIG`):

```toml
[extend]
useDefault = true

[[rules]]
id = "private-word"
regex = '''(?i)(word1|word2)'''
```

## Actions

| Action | What it does |
|--------|-------------|
| `privacy-scan init` | Check dependencies + config |
| `privacy-scan init <repo>` | Also write `<repo>/.privacy-allow` and add it to `.release-exclude` |
| `privacy-scan <repo> [branch]` | Scan (branch defaults to `production`, else `main`) |
| `--verify` | trufflehog check of any secret found |
| `--detail` | List each matched word / email (prints private text) |
| `--allowed` | List where `.privacy-allow` hid a match: entry → file:line |
| `privacy-scan install` / `uninstall` | Create / remove bin + Claude command symlinks |

## What blocks and what warns

- **ships**: the branch's files plus local build output (`.next/static`, `.next/server/app`). Any private word,
  secret or foreign email here **blocks** (exit 1). A branch other than `production` is scanned minus
  its `.release-exclude` paths, so you see what a release of it would ship.
- **history**: every commit and every author/committer email. Findings only **warn**: history can't be
  cleaned without a rewrite.

## `.privacy-allow`

```
word: my-brand                          # this project's own public name, allowed everywhere
word: build-host  in: deploy/*.cjs      # allowed only in these files; elsewhere it still blocks
email: dev@example.com                  # an allowed email (author or in files); fnmatch patterns ok
email: *@example.com
```

Nothing is hidden silently: every match an entry hides is counted (`allowed=N`) and
`--allowed` lists it per entry as `file:line` (history: `file:line @commit`).

GitHub noreply addresses and the repo's local `user.email` are always allowed. Keep the file out of what
ships: `init <repo>` adds it to `.release-exclude`.

Exit codes: 0 clean (warnings allowed) · 1 blocking findings · 2 usage · 4 config missing · 5 gitleaks missing.

## Layout

```
~/tools/projects/privacy-scan/
├── README.md
├── bin/privacy-scan.py
├── commands/privacy-scan.md
└── docs/ (PROJECT.md, STATUS.md)
```
