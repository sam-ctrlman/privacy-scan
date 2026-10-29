#!/usr/bin/env python3
"""privacy-scan — scan a project repo for leaks before it ships.

Usage:
  privacy-scan init                  # check dependencies + config (run once before first use)
  privacy-scan init <repo>           # also write <repo>/.privacy-allow (the repo's exceptions)
  privacy-scan <repo> [branch]       # scan; branch defaults to production, else main
  privacy-scan <repo> [branch] --verify   # + trufflehog: is a found secret still live?
  privacy-scan <repo> [branch] --detail   # per-word / per-email counts (prints private text!)
  privacy-scan <repo> [branch] --allowed  # where .privacy-allow hid a match: entry → file:line
  privacy-scan install | uninstall   # symlinks into ~/.local/bin + ~/.claude/commands

What it checks:
  ships   = the branch's files + the local build output (public/ is in the tree;
            .next/static, .next/server/app). Private words, secrets and foreign
            email addresses here BLOCK (exit 1). A branch other than production
            is scanned minus its .release-exclude paths (what a release would ship).
  history = every commit (gitleaks git --all) + every author/committer email.
            Findings here only WARN: history can't be cleaned without a rewrite.

A private word is a match of the `private-word` rule in the gitleaks config
(default ~/.config/gitleaks/private.toml, override with PRIVACY_SCAN_CONFIG).
<repo>/.privacy-allow lists the repo's exceptions, one per line:
  word: <text>                  a private word that is this project's own public name
  word: <text>  in: <glob>, …   allowed only in those files (fnmatch on the repo path)
  email: <pattern>              an allowed email (author or in files); fnmatch, e.g. *@example.com
Every match an entry hides is still counted (allowed=N) and listed with --allowed.

Output is counts only unless --detail / --allowed. Exit codes: 0 clean (warnings allowed),
1 findings that block, 2 usage, 4 config missing, 5 gitleaks missing.

Scaffolded by `forge`. The tool name is derived from the repo directory, so
nothing here is hardcoded — rename the repo and it follows.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from collections import Counter
from pathlib import Path


def log(tag: str, msg: str) -> None:
    print(f"[{tag}] {msg}", flush=True)


def die(msg: str, code: int = 1):
    log("error", msg)
    sys.exit(code)


TOOL_NAME = Path(__file__).resolve().parent.parent.name
SYMLINK_TARGET = Path.home() / ".local" / "bin" / TOOL_NAME
CLAUDE_COMMAND_TARGET = Path.home() / ".claude" / "commands" / f"{TOOL_NAME}.md"

PRIVATE_CONFIG = Path(os.environ.get("PRIVACY_SCAN_CONFIG",
                                     Path.home() / ".config" / "gitleaks" / "private.toml"))
PRIVATE_RULE = "private-word"
ALLOW_FILE = ".privacy-allow"
NOREPLY = ("*@users.noreply.github.com", "noreply@github.com")
SKIP = re.compile(r"(^|/)(node_modules|\.git|\.claude|\.gemini|\.codex|\.antigravity|\.agents|__pycache__)/")
BUILD_DIRS = (".next/static", ".next/server/app")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.([A-Za-z]{2,})\b")
# x@2x.png, pkg@1.2.3/index.js … look like emails but are file names
NOT_TLD = {"png", "jpg", "jpeg", "gif", "svg", "webp", "avif", "ico", "js", "mjs", "cjs", "css", "map",
           "json", "ts", "tsx", "jsx", "md", "mdx", "html", "txt", "woff", "woff2", "ttf", "otf"}
TEXT_MAX = 5 * 1024 * 1024
ALLOWED_FILES_SHOWN = 10                 # --allowed: files per entry
ALLOWED_LINES_SHOWN = 8                  # --allowed: line numbers per file

# name → (required, pacman, apt, brew); None = not in that manager's main repos
PACKAGES = {
    "gitleaks": (True, "gitleaks", "gitleaks", "gitleaks"),
    "pre-commit": (False, "pre-commit", "pre-commit", "pre-commit"),
    "trufflehog": (False, None, None, "trufflehog"),
    "git-filter-repo": (False, "git-filter-repo", "git-filter-repo", "git-filter-repo"),
}
ROLES = {
    "gitleaks": "scan engine (private words + secrets)",
    "pre-commit": "per-repo hook chain",
    "trufflehog": "--verify: is a found secret still live",
    "git-filter-repo": "history rewrite, only behind its own gate",
}
VERIFY = False


def _command_source() -> Path:
    return Path(__file__).resolve().parent.parent / "commands" / f"{TOOL_NAME}.md"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True).stdout.strip()


# ---------- init: dependencies + config ----------

def _install_hint(missing: list[str]) -> list[str]:
    if shutil.which("pacman"):
        repo = [p for p in missing if PACKAGES[p][1]]
        aur = [p for p in missing if not PACKAGES[p][1]]
        return ([f"sudo pacman -S --needed {' '.join(repo)}"] if repo else []) + \
               ([f"paru -S {' '.join(aur)}   # AUR (or your AUR helper)"] if aur else [])
    if shutil.which("apt"):
        repo = [p for p in missing if PACKAGES[p][2]]
        other = [p for p in missing if not PACKAGES[p][2]]
        return ([f"sudo apt install {' '.join(repo)}"] if repo else []) + \
               [f"{p}: see the project's install docs (not in apt)" for p in other]
    if shutil.which("brew"):
        return [f"brew install {' '.join(missing)}"]
    return [f"install with your package manager: {' '.join(missing)}"]


def check_deps(quiet: bool = False) -> bool:
    """True when every required dependency and the config are in place."""
    ok = True
    missing = []
    for name, (required, *_rest) in PACKAGES.items():
        if shutil.which(name):
            if not quiet:
                log("ok", f"{name:<16} {ROLES[name]}")
            continue
        missing.append(name)
        if required:
            ok = False
            log("error", f"{name:<16} missing (required) — {ROLES[name]}")
        elif not quiet:
            log("notice", f"{name:<16} missing (optional) — {ROLES[name]}")
    if missing and (not ok or not quiet):
        for line in _install_hint(missing):
            log("install", line)
    if not PRIVATE_CONFIG.exists():
        ok = False
        log("error", f"{PRIVATE_CONFIG} missing — it holds the `{PRIVATE_RULE}` rule")
    else:
        mode = PRIVATE_CONFIG.stat().st_mode & 0o777
        if PRIVATE_RULE not in PRIVATE_CONFIG.read_text():
            ok = False
            log("error", f"{PRIVATE_CONFIG} has no `{PRIVATE_RULE}` rule")
        elif mode & 0o077:
            log("notice", f"{PRIVATE_CONFIG} is mode {mode:o}; chmod 600 keeps the word list private")
        elif not quiet:
            log("ok", f"private-word config {PRIVATE_CONFIG}")
    if not quiet:
        hooks = subprocess.run(["git", "config", "--global", "core.hooksPath"],
                               capture_output=True, text=True).stdout.strip()
        hook = Path(os.path.expanduser(hooks)) / "pre-commit" if hooks else None
        if hook and os.access(hook, os.X_OK):
            log("ok", f"global pre-commit hook {hook}")
        else:
            log("notice", "no global pre-commit hook (core.hooksPath) — commits are not checked")
    return ok


def init_repo(repo: Path) -> int:
    allow = repo / ALLOW_FILE
    if allow.exists():
        log("skip", f"{allow} exists")
    else:
        email = _git(repo, "config", "--local", "user.email")
        allow.write_text(
            "# privacy-scan exceptions for this repo. Never ships: listed in .release-exclude.\n"
            "# word: <text>      a private word that is this project's own public name (exact, any case)\n"
            "# email: <pattern>  an allowed email, author or in files (fnmatch, e.g. *@example.com)\n"
            + (f"email: {email}\n" if email else "")
        )
        log("ok", f"wrote {allow}" + ("" if email else " (no local identity — add email: lines)"))
    excl = repo / ".release-exclude"
    if excl.exists():
        text = excl.read_text()
        if ALLOW_FILE in (l.strip() for l in text.splitlines()):
            log("skip", f"{ALLOW_FILE} already in .release-exclude")
        else:
            with excl.open("a") as f:
                f.write(("" if not text or text.endswith("\n") else "\n") + ALLOW_FILE + "\n")
            log("ok", f"added {ALLOW_FILE} to .release-exclude")
    else:
        log("notice", "no .release-exclude — make sure .privacy-allow never ships")
    return 0


def cmd_init(repo: str | None) -> int:
    if not check_deps():
        log("error", "init failed — fix the errors above, then run init again")
        return 5 if not shutil.which("gitleaks") else 4
    log("ok", "dependencies + config ready")
    return init_repo(_repo_path(repo)) if repo else 0


# ---------- scan ----------

def _repo_path(repo: str) -> Path:
    path = Path(repo).expanduser().resolve()
    if not (path / ".git").exists():
        die(f"{path} is not a git repo", code=2)
    return path


def load_allow(repo: Path) -> tuple[dict[str, list[str]], list[str]]:
    """words: word → path globs it is allowed in ([] = the whole repo); emails: fnmatch patterns."""
    words: dict[str, list[str]] = {}
    emails = list(NOREPLY)
    me = _git(repo, "config", "--local", "user.email")
    if me:
        emails.append(me)
    allow = repo / ALLOW_FILE
    if allow.exists():
        for line in allow.read_text().splitlines():
            key, _, value = line.partition(":")
            value = value.strip()
            if line.lstrip().startswith("#") or not value:
                continue
            if key.strip() == "word":
                parts = re.split(r"\s+in:\s*", value, maxsplit=1)
                word, scope = parts[0], parts[1] if len(parts) == 2 else ""
                globs = [g.strip() for g in scope.split(",") if g.strip()]
                words.setdefault(word.strip().lower(), []).extend(globs or [""])
            elif key.strip() == "email":
                emails.append(value.lower())
    return words, emails


def word_allowed(word: str, rel: str, allow_words: dict[str, list[str]]) -> bool:
    globs = allow_words.get(word)
    if globs is None:
        return False
    return any(g == "" or fnmatch.fnmatch(rel, g) for g in globs)


def email_ok(email: str, allowed: list[str]) -> bool:
    return any(fnmatch.fnmatch(email.lower(), pat.lower()) for pat in allowed)


def gitleaks(mode: str, target: Path, log_opts: str | None = None) -> list[dict]:
    # no --redact: matched text stays in memory so the allow list can filter it; never printed by default
    cmd = ["gitleaks", mode, "--no-banner", "--exit-code", "0", "-c", str(PRIVATE_CONFIG),
           "-r", "-", "-f", "json"]
    if log_opts:
        cmd.append(f"--log-opts={log_opts}")
    result = subprocess.run([*cmd, str(target)], capture_output=True, text=True)
    if result.returncode != 0:
        die(f"gitleaks {mode} failed: {result.stderr.strip()[:200]}")
    return json.loads(result.stdout or "[]")


class Section:
    """Findings for one part of the scan; holds matched text in memory only."""

    def __init__(self, name: str, blocks: bool):
        self.name, self.blocks = name, blocks
        self.words: Counter = Counter()
        self.secrets: Counter = Counter()
        self.emails: Counter = Counter()
        # what .privacy-allow hid: entry → location → count (shown so nothing is hidden silently)
        self.allowed: dict[str, Counter] = {}

    def total(self) -> int:
        return sum(self.words.values()) + sum(self.secrets.values()) + sum(self.emails.values())

    def _allow(self, entry: str, where: str) -> None:
        self.allowed.setdefault(entry, Counter())[where] += 1

    def add_leaks(self, findings: list[dict], allow_words: dict[str, list[str]],
                  root: Path | None, prefix: str = "") -> None:
        for f in findings:
            file = f.get("File", "")
            rel = prefix + (os.path.relpath(file, root) if root and file.startswith(str(root)) else file)
            if SKIP.search("/" + rel):
                continue
            if f.get("RuleID") == PRIVATE_RULE:
                word = (f.get("Secret") or f.get("Match") or "").lower()
                if word_allowed(word, rel, allow_words):
                    commit = f.get("Commit", "")
                    self._allow(f"word {word}", f"{rel}:{f.get('StartLine', '?')}"
                                                + (f" @{commit[:7]}" if commit else ""))
                else:
                    self.words[word] += 1
            else:
                self.secrets[f.get("RuleID", "?")] += 1

    def add_emails(self, root: Path, allowed: list[str], prefix: str = "") -> None:
        for path in root.rglob("*"):
            rel = prefix + path.relative_to(root).as_posix()
            if not path.is_file() or SKIP.search("/" + rel) or path.stat().st_size > TEXT_MAX:
                continue
            try:
                text = path.read_text(errors="strict")
            except (UnicodeDecodeError, OSError):
                continue
            for m in EMAIL.finditer(text):
                email = m.group(0).lower()
                if m.group(1).lower() in NOT_TLD:
                    continue
                if email_ok(email, allowed):
                    line = text.count("\n", 0, m.start()) + 1
                    self._allow(f"email {email}", f"{rel}:{line}")
                else:
                    self.emails[email] += 1

    def report(self, detail: bool, show_allowed: bool) -> None:
        n = self.total()
        tag = "ok" if not n else ("error" if self.blocks else "notice")
        verdict = "clean" if not n else ("BLOCK" if self.blocks else "warn")
        hidden = sum(sum(c.values()) for c in self.allowed.values())
        log(tag, f"{self.name:<8} {verdict:<5} private-words={sum(self.words.values())} "
                 f"secrets={sum(self.secrets.values())} emails={sum(self.emails.values())}  "
                 f"allowed={hidden} ({len(self.allowed)} entr{'y' if len(self.allowed) == 1 else 'ies'})"
                 + (f"  rules={','.join(sorted(self.secrets))}" if self.secrets else ""))
        if detail:
            for word, c in self.words.most_common():
                log("detail", f"  {self.name} word  {word}  ×{c}")
            for email, c in self.emails.most_common():
                log("detail", f"  {self.name} email {email}  ×{c}")
        if show_allowed:
            for entry, where in sorted(self.allowed.items()):
                files = Counter(w.split(":", 1)[0] for w in where.elements())
                log("allowed", f"  {self.name} {entry}  ×{sum(where.values())} in {len(files)} file(s)")
                for file, c in files.most_common(ALLOWED_FILES_SHOWN):
                    lines = sorted({w.split(":", 1)[1] for w in where if w.split(":", 1)[0] == file},
                                   key=lambda s: (len(s), s))
                    more = f" +{len(lines) - ALLOWED_LINES_SHOWN}" if len(lines) > ALLOWED_LINES_SHOWN else ""
                    log("allowed", f"      {file}  ×{c}  line {', '.join(lines[:ALLOWED_LINES_SHOWN])}{more}")
                if len(files) > ALLOWED_FILES_SHOWN:
                    log("allowed", f"      … +{len(files) - ALLOWED_FILES_SHOWN} more file(s)")


def default_branch(repo: Path) -> str:
    if _git(repo, "rev-parse", "-q", "--verify", "production"):
        return "production"
    log("notice", "no production branch — scanning main")
    return "main"


def release_excludes(repo: Path, branch: str) -> list[str]:
    text = _git(repo, "show", f"{branch}:.release-exclude")
    if not text and (repo / ".release-exclude").exists():
        text = (repo / ".release-exclude").read_text()
    return [l.strip().lstrip("/") for l in text.splitlines() if l.strip() and not l.strip().startswith("#")]


def strip_excluded(tree: Path, patterns: list[str]) -> int:
    """Drop what a release would strip (prefix match, like release-check). Returns files removed."""
    removed = 0
    for path in sorted(tree.rglob("*"), reverse=True):
        rel = path.relative_to(tree).as_posix()
        if any(rel == p.rstrip("/") or rel.startswith(p) for p in patterns):
            if path.is_file() or path.is_symlink():
                path.unlink()
                removed += 1
            elif path.is_dir() and not any(path.iterdir()):
                path.rmdir()
    return removed


def scan_ships(repo: Path, branch: str, allow_words: dict[str, list[str]], allow_emails: list[str]) -> Section:
    sec = Section("ships", blocks=True)
    with tempfile.TemporaryDirectory(prefix="privacy-scan-") as tmp:
        tree = Path(tmp) / "tree"
        archive = subprocess.run(["git", "-C", str(repo), "archive", branch], capture_output=True)
        if archive.returncode != 0:
            die(f"git archive {branch} failed: {archive.stderr.decode().strip()[:200]}", code=2)
        tar = Path(tmp) / "tree.tar"
        tar.write_bytes(archive.stdout)
        with tarfile.open(tar) as t:
            t.extractall(tree, filter="data")
        tar.unlink()
        if branch != "production":       # preview what a release of this branch would ship
            patterns = release_excludes(repo, branch)
            if patterns:
                n = strip_excluded(tree, patterns)
                log("notice", f"{branch} is not production — left out {n} file(s) on .release-exclude")
            else:
                log("notice", f"{branch} is not production and has no .release-exclude — scanning all of it")
        sec.add_leaks(gitleaks("dir", tree), allow_words, tree)
        sec.add_emails(tree, allow_emails)
        if sec.secrets and VERIFY:
            verify(["filesystem", str(tree)], "ships")
    built = [repo / d for d in BUILD_DIRS if (repo / d).is_dir()]
    for d in built:
        sec.add_leaks(gitleaks("dir", d), allow_words, d, prefix=f"{d.relative_to(repo).as_posix()}/")
        sec.add_emails(d, allow_emails, prefix=f"{d.relative_to(repo).as_posix()}/")
    if not built:
        log("notice", f"no build output ({', '.join(BUILD_DIRS)}) — only the branch files scanned")
    elif _git(repo, "rev-parse", "--abbrev-ref", "HEAD") != branch:
        log("notice", f"build output is from the checkout on {_git(repo, 'rev-parse', '--abbrev-ref', 'HEAD')}, "
                      f"not {branch}")
    return sec


def scan_history(repo: Path, allow_words: dict[str, list[str]], allow_emails: list[str]) -> Section:
    sec = Section("history", blocks=False)
    sec.add_leaks(gitleaks("git", repo, log_opts="--all"), allow_words, None)
    for email in _git(repo, "log", "--all", "--format=%ae%n%ce").split():
        if not email_ok(email, allow_emails):
            sec.emails[email.lower()] += 1
    if sec.secrets and VERIFY:
        verify(["git", f"file://{repo}"], "history")
    return sec


def verify(target: list[str], name: str) -> None:
    if not shutil.which("trufflehog"):
        log("notice", "--verify needs trufflehog (see `privacy-scan init`)")
        return
    result = subprocess.run(["trufflehog", *target, "--only-verified", "--json", "--no-update"],
                            capture_output=True, text=True)
    live = [l for l in result.stdout.splitlines() if l.startswith("{")]
    log("error" if live else "ok", f"{name:<8} trufflehog: {len(live)} verified live secret(s)")


def cmd_scan(repo_arg: str, branch: str | None, detail: bool, show_allowed: bool) -> int:
    # counts only unless --detail: never print a matched private word by default
    if not check_deps(quiet=True):
        die("dependencies or config missing — run `privacy-scan init`",
            code=5 if not shutil.which("gitleaks") else 4)
    repo = _repo_path(repo_arg)
    branch = branch or default_branch(repo)
    if not _git(repo, "rev-parse", "-q", "--verify", branch):
        die(f"no branch {branch} in {repo.name}", code=2)
    words, emails = load_allow(repo)
    if not (repo / ALLOW_FILE).exists():
        log("notice", f"no {ALLOW_FILE} — run `privacy-scan init {repo}` to list this repo's public names")
    log("info", f"{repo.name} @ {branch}  (allow: {len(words)} word(s), {len(emails)} email pattern(s))")
    ships = scan_ships(repo, branch, words, emails)
    history = scan_history(repo, words, emails)
    for sec in (ships, history):
        sec.report(detail, show_allowed)
    if ships.total():
        log("error", f"{repo.name}: what ships leaks — fix before release")
        return 1
    log("ok", f"{repo.name}: what ships is clean" + (" (history has warnings)" if history.total() else ""))
    return 0


# ---------- install / uninstall ----------

def cmd_install() -> int:
    script_path = Path(__file__).resolve()
    mode = script_path.stat().st_mode
    if not (mode & 0o111):
        script_path.chmod(mode | 0o755)
        log("ok", f"made script executable: {script_path}")
    else:
        log("skip", f"script already executable: {script_path}")
    _install_bin_symlink(script_path)
    _install_claude_command()
    return _install_check_path()


def _install_bin_symlink(script_path: Path) -> None:
    SYMLINK_TARGET.parent.mkdir(parents=True, exist_ok=True)
    if SYMLINK_TARGET.is_symlink():
        current = SYMLINK_TARGET.resolve()
        if current == script_path:
            log("skip", f"bin symlink already correct: {SYMLINK_TARGET} -> {script_path}")
            return
        log("info", f"replacing existing bin symlink ({SYMLINK_TARGET} -> {current})")
        SYMLINK_TARGET.unlink()
    elif SYMLINK_TARGET.exists():
        die(f"{SYMLINK_TARGET} exists and is not a symlink — refusing to overwrite")
    SYMLINK_TARGET.symlink_to(script_path)
    log("ok", f"bin symlink created: {SYMLINK_TARGET} -> {script_path}")


def _install_claude_command() -> None:
    source = _command_source()
    if not source.exists():
        log("notice", f"slash command source not found at {source} — skipping Claude integration")
        return
    CLAUDE_COMMAND_TARGET.parent.mkdir(parents=True, exist_ok=True)
    if CLAUDE_COMMAND_TARGET.is_symlink():
        current = CLAUDE_COMMAND_TARGET.resolve()
        if current == source:
            log("skip", f"slash command symlink already correct: {CLAUDE_COMMAND_TARGET} -> {source}")
            return
        log("info", f"replacing existing slash command symlink ({CLAUDE_COMMAND_TARGET} -> {current})")
        CLAUDE_COMMAND_TARGET.unlink()
    elif CLAUDE_COMMAND_TARGET.exists():
        die(f"{CLAUDE_COMMAND_TARGET} exists and is not a symlink — refusing to overwrite")
    CLAUDE_COMMAND_TARGET.symlink_to(source)
    log("ok", f"slash command symlink created: {CLAUDE_COMMAND_TARGET} -> {source}")


def _install_check_path() -> int:
    on_path = shutil.which(TOOL_NAME)
    if on_path:
        log("ok", f"{TOOL_NAME} on PATH: {on_path}")
        return 0
    log("notice", f"{SYMLINK_TARGET.parent} is not on PATH — add this to your shell rc:")
    log("notice", f'  export PATH="{SYMLINK_TARGET.parent}:$PATH"')
    return 0


def cmd_uninstall() -> int:
    script_path = Path(__file__).resolve()
    _uninstall_bin_symlink()
    _uninstall_claude_command()
    log("info", f"to reinstall: python3 {script_path} install")
    return 0


def _uninstall_bin_symlink() -> None:
    if not SYMLINK_TARGET.is_symlink() and not SYMLINK_TARGET.exists():
        log("info", f"no bin symlink at {SYMLINK_TARGET} to remove")
        return
    if not SYMLINK_TARGET.is_symlink():
        die(f"{SYMLINK_TARGET} exists but is not a symlink — refusing to remove")
    target = SYMLINK_TARGET.resolve()
    SYMLINK_TARGET.unlink()
    log("ok", f"removed bin symlink: {SYMLINK_TARGET} (was -> {target})")


def _uninstall_claude_command() -> None:
    if not CLAUDE_COMMAND_TARGET.is_symlink() and not CLAUDE_COMMAND_TARGET.exists():
        log("info", f"no slash command symlink at {CLAUDE_COMMAND_TARGET} to remove")
        return
    if not CLAUDE_COMMAND_TARGET.is_symlink():
        die(f"{CLAUDE_COMMAND_TARGET} exists but is not a symlink — refusing to remove")
    target = CLAUDE_COMMAND_TARGET.resolve()
    CLAUDE_COMMAND_TARGET.unlink()
    log("ok", f"removed slash command symlink: {CLAUDE_COMMAND_TARGET} (was -> {target})")


# ---------- entry point ----------

def main() -> int:
    global VERIFY
    parser = argparse.ArgumentParser(
        prog=TOOL_NAME,
        description="Scan a project repo for leaks (private words, secrets, foreign emails) before it ships.",
        epilog="Actions: init [repo] · <repo> [branch] · install · uninstall",
    )
    parser.add_argument("args", nargs="*", help="init [repo] | <repo> [branch] | install | uninstall")
    parser.add_argument("--verify", action="store_true", help="trufflehog: check found secrets are live")
    parser.add_argument("--detail", action="store_true", help="per-word/email counts (prints private text)")
    parser.add_argument("--allowed", action="store_true",
                        help="where .privacy-allow hid a match: entry → file:line (prints the allowed words)")
    ns = parser.parse_args()
    args = ns.args
    if not args:
        parser.print_help()
        return 2
    if args == ["install"]:
        return cmd_install()
    if args == ["uninstall"]:
        return cmd_uninstall()
    if args[0] == "init" and len(args) <= 2:
        return cmd_init(args[1] if len(args) == 2 else None)
    if len(args) > 2:
        parser.error("too many arguments")
    VERIFY = ns.verify
    return cmd_scan(args[0], args[1] if len(args) == 2 else None, ns.detail, ns.allowed)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("error", "interrupted")
        sys.exit(130)
