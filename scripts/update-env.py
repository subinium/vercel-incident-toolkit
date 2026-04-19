#!/usr/bin/env python3
"""Upload a new value for a single env var, following Vercel's official safe
rotation pattern: update Vercel *before* invalidating the old vendor credential.

Usage:
  python3 scripts/update-env.py <project> <KEY> --from-stdin --apply
  python3 scripts/update-env.py <project> <KEY> --target production,preview --from-stdin --apply
  python3 scripts/update-env.py <project> <KEY> --from-stdin --apply --redeploy

Default behavior:
  - Reads new value from stdin via getpass (echo-suppressed)
  - If the env var exists: PATCH in place (atomic, preserves id + type)
  - If it does not exist: POST with type=sensitive for prod/preview,
    type=encrypted for development (per Vercel constraint that sensitive
    is not available in the development target)
  - Logs to ~/.vercel-security/rotations.json (no plaintext)

NEVER accepts the value as a CLI arg — would land in shell history.

References:
  https://vercel.com/docs/environment-variables/rotating-secrets
  https://vercel.com/docs/environment-variables/sensitive-environment-variables
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from datetime import datetime, timezone

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
            "This shouldn't normally happen; contact Vercel support if it does."
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
    p.add_argument(
        "--from-stdin", action="store_true", help="Read value from stdin (required)"
    )
    p.add_argument(
        "--apply", action="store_true", help="Actually upload (default: dry-run)"
    )
    p.add_argument(
        "--redeploy",
        action="store_true",
        help="Run `vercel --prod --yes` after upload (cd into the project repo first)",
    )
    args = p.parse_args()

    proj, team_id = find_project(args.project)
    targets = [t.strip() for t in args.target.split(",") if t.strip()]

    for t in targets:
        if t not in ("production", "preview", "development"):
            print(
                red(f"Unknown target '{t}'. Valid: production, preview, development.")
            )
            return 1

    print(f"Project: {proj['name']} ({proj['id']})  team={team_id or 'personal'}")
    print(f"Key:     {args.key}")
    print(f"Targets: {targets}")

    existing = [
        e
        for e in list_env(proj["id"], team_id)
        if e["key"] == args.key and any(t in e.get("target", []) for t in targets)
    ]
    print(f"Existing matching entries: {len(existing)}")
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

    if not confirm(f"Upload to {len(targets)} target(s)?"):
        print(red("Aborted."))
        return 1

    log_entries: list[dict] = []

    # Vercel constraint: sensitive is only supported for production + preview.
    # For development target, fall back to type=encrypted.
    def type_for(target_set: list[str]) -> str:
        return (
            "sensitive"
            if all(t in ("production", "preview") for t in target_set)
            else "encrypted"
        )

    # Strategy per existing entry:
    #   - If existing: PATCH value in place (atomic, preserves id + type)
    #   - If no existing with that target combo: POST create
    for e in existing:
        r = api(
            "PATCH",
            f"/v9/projects/{proj['id']}/env/{e['id']}",
            team_id,
            body={"value": new_value},
        )
        log_entries.append(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "project": proj["name"],
                "key": args.key,
                "action": "patch",
                "env_id": e["id"],
                "status": "ok" if "__error__" not in r else "fail",
                "error": r.get("__error__"),
            }
        )

    if not existing:
        # Create fresh
        new_type = type_for(targets)
        r = api(
            "POST",
            f"/v10/projects/{proj['id']}/env",
            team_id,
            body={
                "key": args.key,
                "value": new_value,
                "type": new_type,
                "target": targets,
            },
        )
        log_entries.append(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "project": proj["name"],
                "key": args.key,
                "action": "create",
                "type": new_type,
                "target": targets,
                "status": "ok" if "__error__" not in r else "fail",
                "error": r.get("__error__"),
            }
        )

    rot_log = workspace_dir() / "rotations.json"
    existing_log = json.loads(rot_log.read_text()) if rot_log.exists() else []
    existing_log.extend(log_entries)
    rot_log.write_text(json.dumps(existing_log, indent=2))
    rot_log.chmod(0o600)

    # Drop plaintext from this scope
    new_value = ""
    confirm_value = ""

    any_fail = any(e["status"] != "ok" for e in log_entries)
    if any_fail:
        print(
            red(
                "\n✗ Upload failed — see rotation log. Do NOT invalidate the old vendor credential yet."
            )
        )
        for e in log_entries:
            if e["status"] != "ok":
                print(red(f"  {e['action']}: {e.get('error')}"))
        return 2

    print(green(f"\n✓ {args.key} updated."))
    if args.redeploy:
        import subprocess

        print("  Triggering `vercel --prod --yes`...")
        try:
            r = subprocess.run(["vercel", "--prod", "--yes"], timeout=300)
            if r.returncode != 0:
                print(red("  Redeploy returned non-zero. Check output above."))
        except FileNotFoundError:
            print(red("  `vercel` CLI not on PATH; skipping redeploy."))
        except subprocess.TimeoutExpired:
            print(red("  Redeploy timed out after 5 minutes."))
    else:
        print("  Trigger redeploy: `vercel --prod` (or pass --redeploy next time)")

    print(
        "\n  Per Vercel's official rotation order:\n"
        "  1. ✓ Vercel updated (you are here)\n"
        "  2. [ ] Redeploy production and verify it works with the new value\n"
        "  3. [ ] Only then invalidate the old credential in the vendor's dashboard\n"
        "  4. [ ] `vercel env pull` in the project dir to refresh local `.env`"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
