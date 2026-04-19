#!/usr/bin/env python3
"""Rotate Vercel-side internal-random secrets (NEXTAUTH_SECRET, AUTH_SECRET,
PREVIEW_SECRET, REVALIDATION_SECRET, CRON_SECRET, API_KEY_HMAC_SECRET,
ADMIN_PASSWORD).

Default mode: --dry-run (just prints the plan).
To actually mutate, pass --apply. Even then, prompts y/N before each batch.

External vendor keys (Supabase, DATABASE_URL, OAuth, etc.) are NEVER touched.
Use scripts/update-env.py to upload values you rotated in vendor dashboards.
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

from _common import (
    INTERNAL_RANDOM_KEYS,
    NEVER_ROTATE_PATTERNS,
    api,
    confirm,
    green,
    red,
    workspace_dir,
    yellow,
)


def gen_value(key: str) -> str:
    if key == "ADMIN_PASSWORD":
        alphabet = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#$%^&*"
        return "".join(secrets.choice(alphabet) for _ in range(24))
    return secrets.token_urlsafe(32)


def find_audit() -> Path:
    """Most recent audit snapshot."""
    files = sorted(workspace_dir().glob("audit-*.json"), reverse=True)
    if not files:
        raise SystemExit(
            "No audit snapshot found. Run `python3 scripts/audit.py` first."
        )
    return files[0]


def rotate_one(row: dict, new_value: str) -> dict:
    pid = row["projectId"]
    team = row.get("teamId")
    target = [t for t in row["target"].split(",") if t]
    log = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "project": row["project"],
        "key": row["key"],
        "target": target,
        "old_env_id": row["envId"],
    }
    d = api("DELETE", f"/v10/projects/{pid}/env/{row['envId']}", team)
    if "__error__" in d:
        log["status"] = "delete_failed"
        log["error"] = d
        return log
    c = api(
        "POST",
        f"/v10/projects/{pid}/env",
        team,
        body={
            "key": row["key"],
            "value": new_value,
            "type": "sensitive",
            "target": target,
        },
    )
    if "__error__" in c:
        log["status"] = "create_failed"
        log["error"] = c
        return log
    log["status"] = "ok"
    # Plaintext values are NEVER persisted to the rotation log.
    # ADMIN_PASSWORD is printed to stdout once; the operator must save it
    # to a password manager immediately. There is no recovery path.
    return log


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--apply", action="store_true", help="Actually rotate (default: dry-run)"
    )
    p.add_argument("--audit-file", help="Path to audit snapshot (default: latest)")
    p.add_argument(
        "--include",
        default="",
        help="Comma-separated extra keys to rotate (e.g. MY_CUSTOM_SECRET). "
        "Refuses anything matching NEVER_ROTATE_PATTERNS.",
    )
    p.add_argument(
        "--exclude",
        default="",
        help="Comma-separated keys to skip even if in the default list.",
    )
    args = p.parse_args()

    include = {s.strip() for s in args.include.split(",") if s.strip()}
    exclude = {s.strip() for s in args.exclude.split(",") if s.strip()}

    # Safety: refuse to rotate anything that looks like at-rest encryption or
    # a vendor secret. Users who really want to override must go through
    # scripts/update-env.py instead.
    for k in include:
        if any(p in k.upper() for p in NEVER_ROTATE_PATTERNS):
            print(red(f"Refused: '{k}' matches NEVER_ROTATE_PATTERNS."))
            print(
                red(
                    "Use scripts/update-env.py instead, after rotating in the vendor dashboard."
                )
            )
            return 1

    allowed = (INTERNAL_RANDOM_KEYS | include) - exclude

    snap_path = Path(args.audit_file) if args.audit_file else find_audit()
    rows = json.loads(snap_path.read_text())
    targets = [r for r in rows if r["key"] in allowed]

    if not targets:
        print(green("No internal-random secrets present. Nothing to rotate."))
        return 0

    print(f"Plan: rotate {len(targets)} secret(s) (audit: {snap_path.name})\n")
    for r in sorted(targets, key=lambda r: (r["project"], r["key"])):
        print(f"  - {r['project']:<22} {r['key']:<24} [{r['target']}]")

    print()
    print(yellow("Side effects you must accept:"))
    print("  • NEXTAUTH_SECRET / AUTH_SECRET → all active sessions invalidated")
    print(
        "  • CRON_SECRET → external schedulers calling Vercel Cron will 401 until updated"
    )
    print("  • REVALIDATION_SECRET → CMS webhooks calling /api/revalidate will 401")
    print(
        "  • API_KEY_HMAC_SECRET → consumers using old HMAC will fail signature checks"
    )
    print("  • PREVIEW_SECRET → bookmarked Next.js preview URLs stop working")
    print("  • ADMIN_PASSWORD → new value printed once; save it")
    print()

    if not args.apply:
        print(yellow("Dry-run only. Re-run with --apply to perform rotations."))
        return 0

    if not confirm("Proceed with rotation?"):
        print(red("Aborted."))
        return 1

    log_entries = []
    admin_passwords: list[tuple[str, str]] = (
        []
    )  # (project, plaintext) — printed once, not persisted
    ok = fail = 0
    for r in sorted(targets, key=lambda r: (r["project"], r["key"])):
        new_val = gen_value(r["key"])
        entry = rotate_one(r, new_val)
        log_entries.append(entry)
        mark = green("✓") if entry["status"] == "ok" else red("✗")
        print(f"  {mark} {r['project']:<22} {r['key']:<24} {entry['status']}")
        if entry["status"] == "ok":
            ok += 1
            if r["key"] == "ADMIN_PASSWORD":
                admin_passwords.append((r["project"], new_val))
        else:
            fail += 1
        # Best-effort: drop the plaintext reference from this scope ASAP.
        new_val = ""

    rot_log = workspace_dir() / "rotations.json"
    existing = json.loads(rot_log.read_text()) if rot_log.exists() else []
    existing.extend(log_entries)
    rot_log.write_text(json.dumps(existing, indent=2))
    rot_log.chmod(0o600)

    print(f"\nDone. {green(str(ok))} ok, {red(str(fail)) if fail else '0'} failed.")
    print(f"Rotation log (no plaintext values) appended to {rot_log}")

    if admin_passwords:
        print()
        print(yellow("=" * 60))
        print(yellow("ADMIN_PASSWORD — printed ONCE, never written to disk."))
        print(yellow("Copy to a password manager NOW. There is no recovery."))
        print(yellow("=" * 60))
        for proj, pw in admin_passwords:
            print(f"  {proj}: {pw}")
        print(yellow("=" * 60))
        # Overwrite the local references so they don't linger in process memory
        # any longer than necessary. (Best-effort — Python str interning makes
        # full erasure impossible without ctypes, but we don't keep refs.)
        admin_passwords.clear()

    print()
    print(
        green("Next steps — read runbooks/04-after-rotation.md for the full checklist")
    )
    print("  1. `python3 scripts/handoff-gen.py`    — draft per-project handoff docs")
    print("  2. `vercel logout && vercel login`     — rotate your local CLI token")
    print("  3. `vercel env pull` per project dir   — refresh local `.env`")
    print("  4. Update CI/CD secret mirrors (GitHub Actions etc.) for rotated keys")
    print("  5. `vercel --prod` per project         — force clean redeploy")
    print("  6. Smoke-test production (sign in, DB query, cron tick)")
    print("  7. Rotate external vendor keys ONE at a time (see handoff docs)")
    print("  8. Review Vercel Audit Log for the incident window")
    print("  9. Rotate Deploy Hooks per project")
    print("  10. Continue weekly `scripts/audit.py` diffs for 30 days")
    return 0 if not fail else 2


if __name__ == "__main__":
    sys.exit(main())
