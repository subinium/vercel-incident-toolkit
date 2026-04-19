#!/usr/bin/env python3
"""Run before any other script. Verifies environment is safe to operate in."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from _common import auth_token_path, green, red, workspace_dir, yellow


def check_python() -> bool:
    ok = sys.version_info >= (3, 10)
    print(
        f"  {'✓' if ok else '✗'} Python {sys.version.split()[0]} {'(>=3.10)' if ok else '(NEED >=3.10)'}"
    )
    return ok


def check_vercel_cli() -> bool:
    if not shutil.which("vercel"):
        print(f"  {red('✗')} `vercel` CLI not on PATH. Install with `npm i -g vercel`.")
        return False
    try:
        out = subprocess.run(
            ["vercel", "whoami"], capture_output=True, text=True, timeout=10
        )
    except subprocess.TimeoutExpired:
        print(f"  {red('✗')} `vercel whoami` timed out.")
        return False
    if out.returncode != 0:
        print(f"  {red('✗')} `vercel whoami` failed. Run `vercel login` first.")
        return False
    user = out.stdout.strip()
    print(f"  {green('✓')} Logged in as: {user}")
    return True


def check_auth_file() -> bool:
    try:
        p = auth_token_path()
    except SystemExit as e:
        print(f"  {red('✗')} {e}")
        return False
    mode = p.stat().st_mode & 0o777
    if mode & 0o077:
        print(
            f"  {yellow('!')} auth.json mode {oct(mode)} is too permissive. Run `chmod 600 {p}`."
        )
    else:
        print(f"  {green('✓')} auth.json present, mode {oct(mode)}")
    return True


def check_env_var_token() -> bool:
    import os

    if os.environ.get("VERCEL_TOKEN"):
        print(
            f"  {red('✗')} VERCEL_TOKEN env var is set — unset it to avoid mixing CLI and env auth."
        )
        return False
    print(f"  {green('✓')} VERCEL_TOKEN not set in env (good)")
    return True


def check_workspace() -> bool:
    p = workspace_dir()
    mode = p.stat().st_mode & 0o777
    if mode & 0o077:
        print(f"  {yellow('!')} {p} mode {oct(mode)} is too permissive.")
        try:
            p.chmod(0o700)
            print(f"      → fixed to 0700")
        except PermissionError:
            return False
    print(f"  {green('✓')} workspace {p} ready (mode 0700)")
    return True


def check_no_repo_artifacts() -> bool:
    """Refuse to run if cwd looks like a project repo with a stale rotation log."""
    bad = []
    cwd = Path.cwd()
    for name in ("rotations.json", "audit-snapshot.json", "audit-report.txt"):
        if (cwd / name).exists():
            bad.append(cwd / name)
    if bad:
        print(f"  {red('✗')} Found rotation/audit artifacts in cwd:")
        for b in bad:
            print(f"      {b}  ← move to ~/.vercel-security/ before continuing")
        return False
    print(f"  {green('✓')} No stray rotation artifacts in cwd")
    return True


def main() -> int:
    print("Vercel Incident Toolkit — preflight\n")
    checks = [
        ("Python version", check_python),
        ("Vercel CLI logged in", check_vercel_cli),
        ("Auth file readable", check_auth_file),
        ("No conflicting VERCEL_TOKEN env", check_env_var_token),
        ("Workspace dir secure", check_workspace),
        ("No stray artifacts in cwd", check_no_repo_artifacts),
    ]
    results = []
    for name, fn in checks:
        print(f"{name}:")
        results.append(fn())
        print()
    if all(results):
        print(green("Preflight OK. Safe to proceed."))
        return 0
    print(
        red("Preflight FAILED. Resolve the issues above before running other scripts.")
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
