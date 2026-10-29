# privacy-scan

TODO: one-line description of what privacy-scan automates.

## Install

```sh
git clone <remote-url> ~/tools/projects/privacy-scan
python3 ~/tools/projects/privacy-scan/bin/privacy-scan.py install
```

After install, `privacy-scan` works in any shell and `/privacy-scan` works in Claude Code.

## Actions

| Action | What it does |
|--------|-------------|
| `privacy-scan` / `privacy-scan run` | TODO: the automated workflow |
| `privacy-scan install` | Create bin + Claude command symlinks |
| `privacy-scan uninstall` | Remove both symlinks |

## Layout

```
~/tools/projects/privacy-scan/
├── README.md
├── bin/privacy-scan.py
└── commands/privacy-scan.md
```

## Next steps after scaffolding

1. Edit `bin/privacy-scan.py` — replace the `cmd_run()` body with the deterministic
   steps this tool should automate. Keep each step idempotent (start with a
   `[skip]` fast-path when the work is already done).
2. Update this README and the `description:` in `commands/privacy-scan.md`.
3. `git add -A && git commit` the changes.
4. Before publishing: `forge scan privacy-scan` must exit 0.
5. (Optional) add a remote and `git push -u origin main`.
