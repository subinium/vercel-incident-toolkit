#!/usr/bin/env python3
"""Generate per-project incident handoff docs.

Output: ~/security-incident-<YYYY-MM>-vercel/<project>.md  (mode 0600, dir 0700)

Each doc lists what was auto-rotated, what vendor keys still need manual
rotation, and step-by-step links to the matching vendor runbook. Self-contained
so a fresh Claude session — or a future you — can resume without the toolkit's
in-memory context.
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from _common import (
    HIGH_SECRET_PATTERNS,
    INTERNAL_RANDOM_KEYS,
    workspace_dir,
    write_secure,
)


VENDOR_RULES = [
    ("Supabase", ["SUPABASE_SERVICE", "SUPABASE_JWT"], "vendor-supabase.md"),
    ("Postgres", ["DATABASE_URL", "POSTGRES_URL", "DB_URL"], "vendor-neon.md"),
    (
        "Google OAuth",
        ["GOOGLE_CLIENT", "GOOGLE_OAUTH", "AUTH_GOOGLE"],
        "vendor-google-oauth.md",
    ),
    ("GitHub OAuth", ["GITHUB_CLIENT", "GITHUB_SECRET"], "vendor-generic.md"),
    ("Stripe", ["STRIPE"], "vendor-generic.md"),
    ("OpenAI", ["OPENAI"], "vendor-generic.md"),
    ("Anthropic", ["ANTHROPIC"], "vendor-generic.md"),
    ("Resend/Email", ["RESEND", "SENDGRID", "POSTMARK"], "vendor-generic.md"),
    ("AWS", ["AWS_SECRET", "AWS_ACCESS"], "vendor-generic.md"),
]


def vendor_for(key: str) -> tuple[str, str] | None:
    k = key.upper()
    for name, patterns, runbook in VENDOR_RULES:
        for p in patterns:
            if p in k:
                return name, runbook
    return None


def find_audit() -> Path:
    files = sorted(workspace_dir().glob("audit-*.json"), reverse=True)
    if not files:
        raise SystemExit("No audit snapshot. Run `python3 scripts/audit.py` first.")
    return files[0]


def load_rotations() -> list[dict]:
    p = workspace_dir() / "rotations.json"
    if not p.exists():
        return []
    return json.loads(p.read_text())


def main() -> int:
    snap_path = find_audit()
    rows = json.loads(snap_path.read_text())
    rotations = load_rotations()

    # Output dir
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    out_dir = Path.home() / f"security-incident-{month}-vercel"
    out_dir.mkdir(mode=0o700, exist_ok=True)
    try:
        out_dir.chmod(0o700)
    except PermissionError:
        pass

    # Group rows by project
    by_proj: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_proj[r["project"]].append(r)

    rot_by_proj: dict[str, list[dict]] = defaultdict(list)
    for r in rotations:
        rot_by_proj[r["project"]].append(r)

    affected = []
    for proj, envs in by_proj.items():
        external_pending = []
        public_only = True
        for e in envs:
            if e["key"].upper().startswith(("NEXT_PUBLIC_", "PUBLIC_", "VITE_PUBLIC_")):
                continue
            public_only = False
            v = vendor_for(e["key"])
            if v:
                external_pending.append((e, v))
            elif e["key"] not in INTERNAL_RANDOM_KEYS:
                # Generic high-risk pattern
                if any(p in e["key"].upper() for p in HIGH_SECRET_PATTERNS):
                    external_pending.append(
                        (e, ("Unknown vendor", "vendor-generic.md"))
                    )

        if public_only and not rot_by_proj.get(proj):
            continue  # nothing to do for this project

        affected.append((proj, envs, external_pending, rot_by_proj.get(proj, [])))

    if not affected:
        print("No affected projects. Nothing to write.")
        return 0

    for proj, envs, pending, rotated in affected:
        out = []
        out.append(f"# Incident handoff — `{proj}`")
        out.append("")
        out.append(f"_Generated: {datetime.now(timezone.utc).isoformat()}_")
        out.append(f"_Source audit snapshot: `{snap_path.name}`_")
        out.append("")
        out.append("## What was auto-rotated")
        out.append("")
        if rotated:
            out.append("| When | Key | Status |")
            out.append("|------|-----|--------|")
            for r in rotated:
                out.append(f"| {r['ts']} | `{r['key']}` | {r.get('status', '?')} |")
            # ADMIN_PASSWORD plaintext is intentionally NOT included in this file.
            # The toolkit prints it once to stdout during rotation; the operator
            # is responsible for moving it to a password manager immediately.
            if any(r.get("key") == "ADMIN_PASSWORD" for r in rotated):
                out.append("")
                out.append(
                    "> `ADMIN_PASSWORD` was rotated. The new value was printed to "
                    "stdout during rotation and is **not** stored anywhere. If you "
                    "missed it, run `scripts/rotate-internal.py --apply` again."
                )
        else:
            out.append("_None — this project had no internal-random secrets._")
        out.append("")
        out.append("## Outstanding manual rotations")
        out.append("")
        if pending:
            for env, (vendor, runbook) in pending:
                out.append(f"### `{env['key']}` — {vendor}")
                out.append(f"- Targets: `{env['target']}`")
                out.append(f"- Current type: `{env['type']}`")
                out.append(f"- Runbook: `runbooks/{runbook}`")
                out.append(f"- After rotating in vendor dashboard, run:")
                out.append(f"  ```")
                out.append(
                    f"  python3 scripts/update-env.py {proj} {env['key']} --target {env['target']} --from-stdin --apply"
                )
                out.append(f"  ```")
                out.append("")
        else:
            out.append(
                "_None — all sensitive keys for this project are internal-random and already rotated._"
            )
        out.append("")
        out.append("## Verification checklist")
        out.append("")
        out.append(
            "- [ ] Run `vercel env pull` in the project repo to refresh local `.env`"
        )
        out.append(
            "- [ ] Trigger production redeploy (`vercel --prod` or push a commit)"
        )
        out.append(
            "- [ ] Smoke test: load the production URL, sign in, exercise auth & DB paths"
        )
        out.append(
            "- [ ] Update CI/CD secret mirrors (GitHub Actions, GitLab CI) for any rotated keys"
        )
        out.append(
            "- [ ] Notify users about session invalidation if NEXTAUTH/AUTH_SECRET rotated"
        )
        out.append(
            "- [ ] Check Vercel project Audit Log for unauthorized actions in the incident window"
        )
        out.append("- [ ] Delete stale preview deployments: `vercel remove --safe`")
        out.append("")
        out.append("## Resume from this doc")
        out.append("")
        out.append("If you (or a fresh Claude session) need to pick this up later:")
        out.append("")
        out.append(
            "1. Read this file plus `~/.vercel-security/rotations.json` for full state."
        )
        out.append(
            "2. Re-run `python3 scripts/audit.py` to compare against current state."
        )
        out.append("3. Work through the Outstanding Manual Rotations table above.")
        out.append("4. Mark checkboxes as you complete them.")
        out.append("")

        path = out_dir / f"{proj}.md"
        write_secure(path, "\n".join(out))
        print(f"  wrote {path}")

    # Index file
    idx = [
        "# Incident handoff index",
        "",
        f"_Updated: {datetime.now(timezone.utc).isoformat()}_",
        "",
    ]
    for proj, _, pending, rotated in affected:
        status = []
        if rotated:
            status.append(
                f"{len([r for r in rotated if r.get('status') == 'ok'])} auto-rotated"
            )
        if pending:
            status.append(f"{len(pending)} manual rotation(s) outstanding")
        idx.append(f"- [`{proj}.md`]({proj}.md) — {', '.join(status) or 'review only'}")
    write_secure(out_dir / "README.md", "\n".join(idx) + "\n")
    print(f"\nAll handoff docs in {out_dir}")
    print(
        "Add this directory to your password-manager note or print and store offline."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
