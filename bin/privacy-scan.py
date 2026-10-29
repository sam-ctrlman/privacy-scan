#!/usr/bin/env python3
"""privacy-scan — TODO: one-line description of what this tool automates.

Usage:
  privacy-scan               # run the workflow (default)
  privacy-scan install       # symlink into ~/.local/bin + ~/.claude/commands
  privacy-scan uninstall     # remove those symlinks
  privacy-scan --help

Scaffolded by `forge`. The tool name is derived from the repo directory, so
nothing here is hardcoded — rename the repo and it follows.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess  # noqa: F401  (kept for convenience when adding workflow steps)
import sys
from pathlib import Path


def log(tag: str, msg: str) -> None:
    print(f"[{tag}] {msg}", flush=True)


def die(msg: str, code: int = 1):
    log("error", msg)
    sys.exit(code)


TOOL_NAME = Path(__file__).resolve().parent.parent.name
SYMLINK_TARGET = Path.home() / ".local" / "bin" / TOOL_NAME
CLAUDE_COMMAND_TARGET = Path.home() / ".claude" / "commands" / f"{TOOL_NAME}.md"


def _command_source() -> Path:
    return Path(__file__).resolve().parent.parent / "commands" / f"{TOOL_NAME}.md"


# ---------- the workflow ----------

def cmd_run() -> int:
    # TODO: replace this body with the deterministic steps this tool automates.
    # Keep every step idempotent: begin with a [skip] fast-path when the work
    # is already done. Use log("ok"/"skip"/"install"/"notice"/"error", ...).
    log("notice", f"{TOOL_NAME}: workflow not implemented yet — edit {Path(__file__).resolve()}")
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
    parser = argparse.ArgumentParser(
        prog=TOOL_NAME,
        description="TODO: privacy-scan — describe what this tool does.",
    )
    parser.add_argument(
        "action",
        nargs="?",
        default="run",
        choices=["run", "install", "uninstall"],
        help="run (default) = do the work; install/uninstall = manage symlinks",
    )
    args = parser.parse_args()
    if args.action == "install":
        return cmd_install()
    if args.action == "uninstall":
        return cmd_uninstall()
    return cmd_run()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("error", "interrupted")
        sys.exit(130)
