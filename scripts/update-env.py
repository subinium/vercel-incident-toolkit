#!/usr/bin/env python3
"""Upload a new value for a single env var as type=sensitive.

Use after rotating a key in a vendor dashboard (Supabase, OAuth, DB, etc.).

Usage:
  python3 scripts/update-env.py <project> <KEY> --from-stdin
  python3 scripts/update-env.py <project> <KEY> --target production,preview --from-stdin

Default behavior:
  - Reads new value from stdin (echo-suppressed via getpass)
  - Deletes existing entries for that KEY+target combo
  - Creates new entry with type=sensitive
  - Logs to ~/.vercel-security/rotations.json

NEVER pass the value as a CLI arg — it would land in shell history.
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from _common import (
    api,
    confirm,
    green,
    list_env,
    list_projects,
    list_teams,
    red,
    workspace_dir,
    yellow,
)


def find_project(name: str) -> tuple[dict, str | None]:
    """Search across personal + all teams for a project by name."""
    teams = [(None, "personal")] + [(t["id"], t["slug"]) for t in list_teams()]
    matches = []
    for team_id, scope in teams:
        for p in list_projects(team_id):
            if p["name"] == name:
                matches.append((p, team_id, scope))
    if not matches:
        raise SystemExit(f"Project '{name}' not found in any scope.")
    if len(set(m[0]["id"] for m in matches)) > 1:
        raise SystemExit(
            f"Project name '{name}' resolves to multiple project IDs. "
            "Please specify --project-id and --team-id explicitly."
        )
    return matches[0][0], matches[0][1]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("project", help="Project name")
    p.add_argument("key", help="Env var key")
    p.add_argument(
        "--target",
        default="production",
        help="Comma-separated targets (default: production)",
    )
    p.add_argument("--from-stdin", action="store_true", help="Read value from stdin")
    p.add_argument(
        "--apply",
        action="store_true",
        help="Actually upload (default: dry-run)",
    )
    p.add_argument(
        "--redeploy",
        action="store_true",
        help="Trigger `vercel --prod` after successful upload (requires being cd'd into the project repo)",
    )
    args = p.parse_args()

    proj, team_id = find_project(args.project)
    targets = [t.strip() for t in args.target.split(",") if t.strip()]
    print(f"Project: {proj['name']} ({proj['id']})  team={team_id or 'personal'}")
    print(f"Key:     {args.key}")
    print(f"Targets: {targets}")

    existing = [
        e
        for e in list_env(proj["id"], team_id)
        if e["key"] == args.key and any(t in e.get("target", []) for t in targets)
    ]
    print(f"Existing entries to delete: {len(existing)}")
    for e in existing:
        print(f"  - id={e['id']}  type={e['type']}  target={e.get('target')}")

    if not args.apply:
        print(yellow("\nDry-run only. Re-run with --apply to upload."))
        return 0

    if not args.from_stdin:
        print(red("Refusing to accept value from CLI args. Pass --from-stdin."))
        return 1
    new_value = getpass.getpass("New value (input hidden): ").strip()
    if not new_value:
        print(red("Empty value. Aborted."))
        return 1
    confirm_value = getpass.getpass("Re-enter to confirm: ").strip()
    if new_value != confirm_value:
        print(red("Values do not match. Aborted."))
        return 1

    if not confirm(f"Upload to {len(targets)} target(s) as sensitive?"):
        print(red("Aborted."))
        return 1

    log_entries = []
    for e in existing:
        d = api("DELETE", f"/v10/projects/{proj['id']}/env/{e['id']}", team_id)
        log_entries.append(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "project": proj["name"],
                "key": args.key,
                "action": "delete",
                "old_env_id": e["id"],
                "status": "ok" if "__error__" not in d else "fail",
                "error": d.get("__error__"),
            }
        )

    c = api(
        "POST",
        f"/v10/projects/{proj['id']}/env",
        team_id,
        body={
            "key": args.key,
            "value": new_value,
            "type": "sensitive",
            "target": targets,
        },
    )
    log_entries.append(
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "project": proj["name"],
            "key": args.key,
            "action": "create",
            "type": "sensitive",
            "target": targets,
            "status": "ok" if "__error__" not in c else "fail",
            "error": c.get("__error__"),
        }
    )

    rot_log = workspace_dir() / "rotations.json"
    existing_log = json.loads(rot_log.read_text()) if rot_log.exists() else []
    existing_log.extend(log_entries)
    rot_log.write_text(json.dumps(existing_log, indent=2))
    rot_log.chmod(0o600)

    last = log_entries[-1]
    if last["status"] != "ok":
        print(red(f"\n✗ Upload failed: {last.get('error')}"))
        return 2

    print(green(f"\n✓ {args.key} uploaded as sensitive."))
    if args.redeploy:
        import subprocess

        print("  Triggering `vercel --prod`...")
        try:
            r = subprocess.run(["vercel", "--prod", "--yes"], timeout=300)
            if r.returncode != 0:
                print(red("  Redeploy command returned non-zero. Check output above."))
        except FileNotFoundError:
            print(red("  `vercel` CLI not on PATH; skipping redeploy."))
        except subprocess.TimeoutExpired:
            print(red("  Redeploy timed out after 5 minutes; check Vercel dashboard."))
    else:
        print(
            f"  Trigger redeploy: `vercel --prod` (or pass --redeploy) or push a commit."
        )
    print(f"  Refresh local: `vercel env pull` in the project dir.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
