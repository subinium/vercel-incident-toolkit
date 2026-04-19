#!/usr/bin/env python3
"""Append toolkit artifact patterns to a project's ignore files.

Touches: .gitignore, .vercelignore, .dockerignore, .npmignore (creates if missing).
Idempotent: only adds patterns that aren't already present.

Usage:
  python3 scripts/ignore-setup.py /path/to/repo
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PATTERNS = [
    ".vercel-security/",
    "security-incident-*-vercel/",
    "SECURITY-INCIDENT-*.md",
    "rotations.json",
    "rollback-*.json",
    "audit-*.json",
    "audit-*.txt",
    "*.token",
    "*.tokens",
]

TARGET_FILES = [
    ".gitignore",
    ".vercelignore",
    ".dockerignore",
    ".npmignore",
]

HEADER = (
    "# vercel-incident-toolkit artifacts (added automatically — do not commit secrets)"
)


def update_ignore(path: Path) -> tuple[int, int]:
    existing_lines = path.read_text().splitlines() if path.exists() else []
    existing_set = set(line.strip() for line in existing_lines)
    added = [p for p in PATTERNS if p not in existing_set]
    if not added:
        return 0, len(existing_lines)
    new_lines = list(existing_lines)
    if new_lines and new_lines[-1] != "":
        new_lines.append("")
    new_lines.append(HEADER)
    new_lines.extend(added)
    path.write_text("\n".join(new_lines) + "\n")
    return len(added), len(new_lines)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("repo", help="Path to repository root")
    args = p.parse_args()
    root = Path(args.repo).expanduser().resolve()
    if not root.is_dir():
        raise SystemExit(f"Not a directory: {root}")

    print(f"Updating ignore files in {root}\n")
    for fname in TARGET_FILES:
        path = root / fname
        added, total = update_ignore(path)
        if added:
            print(f"  + {fname}: added {added} pattern(s) (total {total} lines)")
        else:
            print(f"  · {fname}: up to date")
    print(
        "\nDone. Verify with: git status (no toolkit artifacts should show as untracked)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
