#!/usr/bin/env python3
"""Rotate Vercel-side internal-random secrets.

Default: NEXTAUTH_SECRET, AUTH_SECRET, SESSION_SECRET, COOKIE_SECRET,
PAYLOAD_SECRET, PREVIEW_SECRET, REVALIDATION_SECRET, CRON_SECRET,
API_KEY_HMAC_SECRET, HMAC_SECRET, ADMIN_PASSWORD.

Method: uses Vercel's documented PATCH /v9/projects/<id>/env/<env-id>
endpoint to update the value atomically in-place. This keeps the existing
env var id and type intact — no window where the variable is missing. If you
also want to upgrade types to 'sensitive', run scripts/harden-to-sensitive.py
as a separate pass (that path is delete+create per Vercel's documented rule:
'to mark an existing environment variable as sensitive, remove and re-add it').

Safety:
  - Default mode is --dry-run. Must pass --apply to mutate.
  - Even with --apply, prompts y/N before touching anything.
  - Re-fetches each env var before mutation to catch stale snapshots.
  - Retries 429/5xx with exponential backoff; never retries 4xx rejections.
  - External vendor keys (Supabase, DATABASE_URL, OAuth, etc.) are NEVER
    touched here. Use scripts/update-env.py after rotating in the vendor
    dashboard, following Vercel's official rotation order (update Vercel
    before invalidating the vendor's old credential).

References:
  https://vercel.com/docs/environment-variables/rotating-secrets
  https://vercel.com/docs/environment-variables/sensitive-environment-variables
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
    get_env,
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
    files = sorted(workspace_dir().glob("audit-*.json"), reverse=True)
    if not files:
        raise SystemExit(
            "No audit snapshot found. Run `python3 scripts/audit.py` first."
        )
    return files[0]


def rotate_one(row: dict, new_value: str) -> dict:
    """PATCH the value atomically. Keeps env id + type. Re-verifies before mutate."""
    pid = row["projectId"]
    team = row.get("teamId")
    env_id = row["envId"]
    log = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "project": row["project"],
        "key": row["key"],
        "target": [t for t in row["target"].split(",") if t],
        "env_id": env_id,
        "method": "PATCH",
    }
    # Re-fetch to verify the snapshot is still current.
    current = get_env(pid, env_id, team)
    if current is None:
        log["status"] = "not_found"
        log["error"] = "env var missing at mutation time — rerun audit"
        return log
    if current.get("key") != row["key"]:
        log["status"] = "mismatch"
        log["error"] = f"expected key={row['key']!r}, found {current.get('key')!r}"
        return log
    # PATCH — atomic value update. Body intentionally minimal to avoid touching type.
    r = api(
        "PATCH",
        f"/v9/projects/{pid}/env/{env_id}",
        team,
        body={"value": new_value},
    )
    if "__error__" in r:
        log["status"] = "patch_failed"
        log["error"] = r
        return log
    log["status"] = "ok"
    log["type_after"] = current.get("type")  # informational — we didn't change it
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

    for k in include:
        if any(pat in k.upper() for pat in NEVER_ROTATE_PATTERNS):
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

    print(f"Plan: rotate {len(targets)} secret(s) (audit: {snap_path.name})")
    print(
        "Method: atomic PATCH of value only — keeps env id and type. "
        "Run `scripts/harden-to-sensitive.py` separately to upgrade types.\n"
    )
    for r in sorted(targets, key=lambda r: (r["project"], r["key"])):
        print(f"  - {r['project']:<22} {r['key']:<24} [{r['target']}] type={r['type']}")

    print()
    print(yellow("Side effects you must accept:"))
    print("  • NEXTAUTH_SECRET / AUTH_SECRET / SESSION_SECRET / COOKIE_SECRET")
    print("      → all active sessions invalidated; users must re-login")
    print("  • CRON_SECRET → external schedulers calling Vercel Cron will 401")
    print("  • REVALIDATION_SECRET → CMS webhooks calling /api/revalidate will 401")
    print("  • HMAC_SECRET / API_KEY_HMAC_SECRET → consumers using old HMAC fail")
    print("  • PREVIEW_SECRET → bookmarked Next.js preview URLs stop working")
    print("  • ADMIN_PASSWORD → new value printed once; save to password manager NOW")
    print()

    if not args.apply:
        print(yellow("Dry-run only. Re-run with --apply to perform rotations."))
        return 0

    if not confirm("Proceed with rotation?"):
        print(red("Aborted."))
        return 1

    log_entries = []
    admin_passwords: list[tuple[str, str]] = []
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
            # For any non-OK: print the new value so the operator can manually
            # set it via the Vercel dashboard. We do NOT persist it.
            print(
                red(
                    f"      RECOVER: manually set {r['key']} for {r['project']} → {new_val}"
                )
            )
        new_val = ""  # drop plaintext reference

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
        admin_passwords.clear()

    print()
    print(green("Next steps — see runbooks/04-after-rotation.md for the full playbook"))
    print("  1. `python3 scripts/handoff-gen.py`  — draft per-project handoff docs")
    print("  2. Revoke all Vercel tokens via the dashboard (not just `vercel logout`)")
    print("  3. Verify 2FA on every team member; remove ex-teammates")
    print("  4. `vercel env pull` per project       — refresh local `.env`")
    print("  5. Update CI/CD secret mirrors (GitHub Actions etc.)")
    print("  6. `vercel --prod` per project         — force cold-start redeploy")
    print("  7. Smoke-test production (sign in, DB query, cron tick)")
    print("  8. Rotate external vendor keys ONE AT A TIME (see handoff docs)")
    print("  9. Review Vercel Audit Log for the incident window")
    print(" 10. Rotate Deploy Hooks per project")
    print(" 11. Continue weekly `scripts/audit.py` diffs for 30 days")
    return 0 if not fail else 2


if __name__ == "__main__":
    sys.exit(main())
