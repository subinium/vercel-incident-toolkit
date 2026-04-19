#!/usr/bin/env python3
"""Convert every non-sensitive env var to type=sensitive, preserving values.

This is the "Flow B" hardening step. After this runs, the values can no longer
be read from the Vercel dashboard or API — to see them again, you must rotate.

Mechanism:
  1. Per project, run `vercel env pull` into a temp dir to obtain plaintext.
  2. For each env var that is currently 'encrypted' or 'plain' (NOT sensitive,
     NOT NEXT_PUBLIC_*), call DELETE then POST with type=sensitive.
  3. Wipe the temp file immediately.

Default mode: --dry-run. Use --apply to mutate.

Caveats — must surface to the user:
  * `vercel env pull` writes a plaintext .env to a temp dir. We chmod it 0600
    and unlink immediately, but if the script is killed mid-run the file may
    persist. Run in a private workstation only.
  * `NEXT_PUBLIC_*` vars are skipped — they're public by design.
  * Conversion preserves values. If a value was already exposed in the Vercel
    breach, hardening alone does NOT mitigate; you must rotate.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from _common import (
    api,
    confirm,
    green,
    is_public_key,
    list_env,
    list_projects,
    list_teams,
    red,
    workspace_dir,
    yellow,
)


def pull_envs_for_project(project_name: str, team_slug: str | None) -> dict[str, str]:
    """Use `vercel env pull` to get plaintext values. Returns {KEY: value}.
    Cleans up plaintext file immediately."""
    tmpdir = tempfile.mkdtemp(prefix="vit-")
    out_file = Path(tmpdir) / ".env"
    cmd = [
        "vercel",
        "env",
        "pull",
        str(out_file),
        "--cwd",
        tmpdir,
        "--environment",
        "production",
        "--yes",
    ]
    if team_slug:
        cmd.extend(["--scope", team_slug])
    # We need to link the project into tmpdir first
    link_cmd = ["vercel", "link", "--project", project_name, "--yes", "--cwd", tmpdir]
    if team_slug:
        link_cmd.extend(["--scope", team_slug])
    try:
        subprocess.run(link_cmd, check=True, capture_output=True, timeout=30)
        subprocess.run(cmd, check=True, capture_output=True, timeout=30)
        if not out_file.exists():
            return {}
        out_file.chmod(0o600)
        result: dict[str, str] = {}
        for line in out_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, _, v = line.partition("=")
            v = v.strip().strip('"').strip("'")
            result[k.strip()] = v
        return result
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--scope", help="Limit to one team slug (optional)")
    p.add_argument("--project", help="Limit to one project name (optional)")
    args = p.parse_args()

    teams = list_teams()
    scopes: list[tuple[str | None, str]] = [(None, "personal")]
    scopes.extend((t["id"], t["slug"]) for t in teams)
    if args.scope:
        scopes = [(tid, slug) for tid, slug in scopes if slug == args.scope]
        if not scopes:
            raise SystemExit(f"Scope '{args.scope}' not found.")

    plan: list[tuple[dict, str | None, dict]] = []  # (project, team_id, env_row)
    skipped_dev: list[tuple[str, str, list[str]]] = []  # (project, key, targets)
    for team_id, slug in scopes:
        for proj in list_projects(team_id):
            if args.project and proj["name"] != args.project:
                continue
            for e in list_env(proj["id"], team_id):
                if e["type"] == "sensitive":
                    continue
                if is_public_key(e["key"]):
                    continue
                # Vercel constraint: sensitive is not available for the
                # development target. If the env var includes development,
                # we skip — user must manually split it into (prod+preview)
                # and (dev) entries, or accept that development stays encrypted.
                targets = e.get("target", [])
                if "development" in targets:
                    skipped_dev.append((proj["name"], e["key"], targets))
                    continue
                plan.append((proj, team_id, e))

    if not plan and not skipped_dev:
        print(green("Nothing to harden. Already all sensitive (or public)."))
        return 0

    if skipped_dev:
        print(
            yellow(
                f"Skipping {len(skipped_dev)} env var(s) with development target "
                "(Vercel constraint: sensitive is not available for development):"
            )
        )
        for pname, key, targets in sorted(skipped_dev):
            print(f"  · {pname:<28} {key:<36} target={targets}")
        print(
            yellow(
                "  To harden these: manually split in the dashboard into (prod+preview, sensitive) "
                "and (development, encrypted), or leave as-is."
            )
        )
        print()

    if not plan:
        print(
            green(
                "No harden-able env vars remain (all are sensitive, public, or dev-only)."
            )
        )
        return 0

    print(f"Plan: convert {len(plan)} env var(s) to sensitive.\n")
    by_proj: dict[str, list[str]] = {}
    for proj, _, e in plan:
        by_proj.setdefault(proj["name"], []).append(e["key"])
    for pname, keys in sorted(by_proj.items()):
        print(f"  {pname:<28} {len(keys)} key(s): {', '.join(sorted(set(keys)))}")
    print()
    print(yellow("This rewrites every non-sensitive env var. Side effects:"))
    print("  • Each value is briefly written to a 0600 temp file before re-upload.")
    print("  • After this, dashboard/API will not show values — only the env name.")
    print(
        "  • Hardening preserves values; if values were leaked, you must ROTATE separately."
    )
    print()
    if not args.apply:
        print(yellow("Dry-run. Re-run with --apply to perform conversions."))
        return 0
    if not confirm("Proceed?"):
        print(red("Aborted."))
        return 1

    log_entries = []
    ok = fail = 0
    # Pull values per project to minimize CLI calls
    pulled_cache: dict[tuple[str, str | None], dict[str, str]] = {}

    for proj, team_id, e in plan:
        team_slug = next((s for tid, s in scopes if tid == team_id), None)
        cache_key = (proj["name"], team_slug)
        if cache_key not in pulled_cache:
            try:
                pulled_cache[cache_key] = pull_envs_for_project(proj["name"], team_slug)
            except subprocess.CalledProcessError as ex:
                print(
                    red(
                        f"  ✗ env pull failed for {proj['name']}: {ex.stderr.decode()[:120]}"
                    )
                )
                pulled_cache[cache_key] = {}
        values = pulled_cache[cache_key]
        if e["key"] not in values:
            print(
                red(f"  ✗ {proj['name']:<22} {e['key']:<28} value not in pull (skip)")
            )
            fail += 1
            continue
        # delete + recreate as sensitive
        d = api("DELETE", f"/v10/projects/{proj['id']}/env/{e['id']}", team_id)
        if "__error__" in d:
            print(red(f"  ✗ {proj['name']:<22} {e['key']:<28} delete failed"))
            log_entries.append(
                {
                    "project": proj["name"],
                    "key": e["key"],
                    "status": "delete_failed",
                    "error": d,
                }
            )
            fail += 1
            continue
        c = api(
            "POST",
            f"/v10/projects/{proj['id']}/env",
            team_id,
            body={
                "key": e["key"],
                "value": values[e["key"]],
                "type": "sensitive",
                "target": e.get("target", ["production"]),
            },
        )
        if "__error__" in c:
            print(red(f"  ✗ {proj['name']:<22} {e['key']:<28} create failed"))
            log_entries.append(
                {
                    "project": proj["name"],
                    "key": e["key"],
                    "status": "create_failed",
                    "error": c,
                }
            )
            fail += 1
            continue
        print(green(f"  ✓ {proj['name']:<22} {e['key']:<28} sensitive"))
        log_entries.append(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "project": proj["name"],
                "key": e["key"],
                "old_env_id": e["id"],
                "status": "ok",
                "action": "harden",
            }
        )
        ok += 1

    rot_log = workspace_dir() / "rotations.json"
    existing = json.loads(rot_log.read_text()) if rot_log.exists() else []
    existing.extend(log_entries)
    rot_log.write_text(json.dumps(existing, indent=2))
    rot_log.chmod(0o600)

    print(f"\nDone. {green(str(ok))} ok, {red(str(fail)) if fail else '0'} failed.")
    print("Re-run `python3 scripts/audit.py` to confirm 0 non-sensitive remaining.")
    return 0 if not fail else 2


if __name__ == "__main__":
    sys.exit(main())
