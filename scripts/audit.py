#!/usr/bin/env python3
"""Read-only inventory of Vercel env vars across all scopes.

Output:
  ~/.vercel-security/audit-<UTC>.json   full machine-readable inventory
  stdout                                human-readable summary

Never mutates anything. Safe to run anytime.
"""

from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from _common import (
    green,
    list_env,
    list_projects,
    list_teams,
    severity,
    workspace_dir,
    yellow,
)


def main() -> int:
    teams = list_teams()
    scopes: list[tuple[str, str | None]] = [("personal", None)]
    scopes.extend((t["slug"], t["id"]) for t in teams)
    print(f"Scopes: {len(scopes)} (personal + {len(teams)} team(s))\n")

    rows: list[dict] = []
    errors: list[str] = []

    for scope_name, team_id in scopes:
        try:
            projects = list_projects(team_id)
        except SystemExit as e:
            errors.append(f"{scope_name}: {e}")
            continue
        print(f"  {scope_name:<20} {len(projects)} projects")

        with ThreadPoolExecutor(max_workers=8) as ex:
            futs = {ex.submit(list_env, p["id"], team_id): p for p in projects}
            for fut in as_completed(futs):
                p = futs[fut]
                try:
                    envs = fut.result()
                except SystemExit as e:
                    errors.append(f"{scope_name}/{p['name']}: {e}")
                    continue
                for e in envs:
                    rows.append(
                        {
                            "scope": scope_name,
                            "project": p["name"],
                            "projectId": p["id"],
                            "teamId": team_id,
                            "key": e["key"],
                            "type": e["type"],
                            "target": ",".join(e.get("target", [])),
                            "envId": e.get("id"),
                            "severity": severity(e["key"], e["type"]),
                        }
                    )

    # Dedupe — personal + team scopes can return same project twice
    seen, uniq = set(), []
    for r in rows:
        k = (r["projectId"], r["envId"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(r)

    counts = {"OK": 0, "HIGH": 0, "MED": 0, "LOW-PLAIN": 0}
    for r in uniq:
        counts[r["severity"]] = counts.get(r["severity"], 0) + 1

    print()
    print("Summary")
    print("-------")
    print(f"  Total env vars (deduped): {len(uniq)}")
    print(f"  {green('Sensitive (OK)')}:        {counts['OK']}")
    print(f"  {yellow('HIGH (rotate first)')}:    {counts['HIGH']}")
    print(f"  MED  (encrypted, generic): {counts['MED']}")
    print(f"  LOW-PLAIN:                 {counts['LOW-PLAIN']}")
    if errors:
        print(f"  Errors: {len(errors)}")
        for e in errors:
            print(f"    {e}")

    if counts["HIGH"]:
        print("\nHIGH-severity keys (vendor-secret patterns):")
        high = sorted(
            (r for r in uniq if r["severity"] == "HIGH"),
            key=lambda r: (r["project"], r["key"]),
        )
        for r in high:
            print(f"  {r['project']:<28} {r['key']:<36} [{r['target']}]")

    if counts["LOW-PLAIN"]:
        print("\nPLAINTEXT (visible to anyone with team read access):")
        for r in [r for r in uniq if r["severity"] == "LOW-PLAIN"]:
            print(f"  {r['project']:<28} {r['key']:<36} [{r['target']}]")

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = workspace_dir() / f"audit-{ts}.json"
    out_path.write_text(json.dumps(uniq, indent=2))
    out_path.chmod(0o600)
    print(f"\nFull inventory: {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
