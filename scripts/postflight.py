#!/usr/bin/env python3
"""After running incident response, verify the state is clean.

Checks:
  - Re-runs audit; reports HIGH/MED/PLAIN counts
  - Diffs against the previous audit snapshot
  - Flags any newly-appearing env vars or projects (suspicious)
  - Reminds the user of the manual checklist (audit log review, 2FA, etc.)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from _common import green, red, workspace_dir, yellow


def main() -> int:
    snaps = sorted(workspace_dir().glob("audit-*.json"), reverse=True)
    if len(snaps) < 2:
        print(
            yellow(
                "Need at least 2 audit snapshots to diff. Run `python3 scripts/audit.py` first, then again after rotations."
            )
        )
        return 0

    new_path, old_path = snaps[0], snaps[1]
    new = json.loads(new_path.read_text())
    old = json.loads(old_path.read_text())
    print(f"Diffing {old_path.name} → {new_path.name}\n")

    def key(r):
        return (r.get("projectId"), r.get("envId"))

    new_keys = {key(r): r for r in new}
    old_keys = {key(r): r for r in old}

    added = [r for k, r in new_keys.items() if k not in old_keys]
    removed = [r for k, r in old_keys.items() if k not in new_keys]
    type_changed = []
    for k, r in new_keys.items():
        if k in old_keys and old_keys[k].get("type") != r.get("type"):
            type_changed.append((old_keys[k], r))

    print(f"  Added env vars:   {len(added)}")
    print(f"  Removed env vars: {len(removed)}")
    print(f"  Type changed:     {len(type_changed)}")
    print()

    if added:
        print(yellow("New env vars (verify each is intentional):"))
        for r in added:
            print(f"  + {r['project']:<24} {r['key']:<32} type={r['type']}")
        print()

    if type_changed:
        print(green("Type transitions:"))
        for old_r, new_r in type_changed:
            print(
                f"  ~ {new_r['project']:<24} {new_r['key']:<32} {old_r['type']} → {new_r['type']}"
            )
        print()

    # Severity totals
    new_sev = {"OK": 0, "HIGH": 0, "MED": 0, "LOW-PLAIN": 0}
    for r in new:
        new_sev[r["severity"]] = new_sev.get(r["severity"], 0) + 1
    print("Current severity counts:")
    for k, v in new_sev.items():
        marker = green("✓") if k == "OK" else yellow("!") if v else green("✓")
        print(f"  {marker} {k}: {v}")
    print()

    print("Manual checks (toolkit cannot do these for you):")
    print(
        "  [ ] Vercel team Audit Log: scan for unauthorized member/token/project actions in incident window"
    )
    print("  [ ] Team Members: every member has 2FA enabled")
    print("  [ ] Tokens: revoke any old / unrecognized access tokens")
    print(
        "  [ ] Deploy Hooks: rotate every deploy hook URL (anyone with the URL can trigger builds)"
    )
    print(
        "  [ ] Recent production deploys: diff git SHA vs deployed; force redeploy from known-good commit"
    )
    print(
        "  [ ] vercel.json: diff against last known-good revision (rewrites/headers/regions)"
    )
    print("  [ ] Stale preview deployments: `vercel remove --safe` for old previews")
    print(
        "  [ ] Update CI/CD secret mirrors (GitHub Actions, GitLab CI) for every rotated key"
    )
    print("  [ ] Notify users of session invalidation if NEXTAUTH/AUTH_SECRET rotated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
