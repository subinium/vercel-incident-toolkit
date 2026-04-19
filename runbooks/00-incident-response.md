# Runbook 00 — Incident response (end to end)

When you believe a Vercel breach affects you, work this runbook top to bottom. Don't skip steps. Don't batch external rotations.

## Minute 0–5

1. Run preflight: `python3 scripts/preflight.py`. Fix any errors before continuing.
2. **Rotate the local CLI token immediately.**
   ```
   vercel logout
   vercel login
   ```
   This invalidates the token even if it had already been exfiltrated.
3. Snapshot current state: `python3 scripts/audit.py`.

## Minute 5–15

4. Apply ignore patterns to every affected user repo (do this before any handoff doc gets copied):
   ```
   python3 scripts/ignore-setup.py /path/to/repo
   ```
5. Rotate internal-random secrets (dry-run first, then `--apply`):
   ```
   python3 scripts/rotate-internal.py
   python3 scripts/rotate-internal.py --apply
   ```
6. Save any `ADMIN_PASSWORD` shown on stdout into a password manager **immediately**. The toolkit will never re-emit it.

## Minute 15–60

7. Generate per-project handoff docs:
   ```
   python3 scripts/handoff-gen.py
   ```
   Files land in `~/security-incident-<YYYY-MM>-vercel/`. Review the index.

8. For each external-vendor key listed in the handoff:
   - Open the matching `runbooks/vendor-*.md`
   - Rotate in the vendor dashboard
   - Upload the new value: `python3 scripts/update-env.py <project> <KEY> --from-stdin --apply`
   - Trigger a production redeploy and smoke test
   - **Then** move to the next vendor key — never batch

9. After every key is rotated, run postflight:
   ```
   python3 scripts/postflight.py
   ```

## Manual checks postflight cannot do for you

- Vercel team **Audit Log** — scan for unauthorized member adds, token creations, deploy protection changes during the incident window
- Every team member has 2FA enabled
- Every personal access token is recognized; revoke any that aren't
- Every Deploy Hook URL has been rotated (Project → Settings → Git → Deploy Hooks)
- `vercel.json` diffed against last known-good revision (rewrites, headers, function regions)
- Recent production deploys: deployed git SHA matches HEAD; force a clean redeploy from a known-good commit
- Stale preview deployments removed: `vercel remove --safe`
- CI/CD secret mirrors (GitHub Actions, GitLab CI) updated for every rotated key
- Users notified about session invalidation if `NEXTAUTH_SECRET` / `AUTH_SECRET` rotated
- Backup-sync exclusions: `~/.vercel-security/` and `~/security-incident-*-vercel/` are not synced to iCloud Drive, Dropbox, OneDrive, or any other off-machine location

## When to declare the incident closed

- Postflight reports 0 HIGH severity remaining
- Audit log shows no unexpected actions for 7 consecutive days post-rotation
- All downstream consumers (CI, webhooks, schedulers) are confirmed working with new values
- Vercel publishes a post-mortem and your impacted-customer status is confirmed

## When to escalate

- Audit log shows actions you didn't take and can't attribute to a teammate
- A deployment was published from a commit you don't recognize
- A team member or token appears that no one claims
- Any external vendor (Supabase, Neon, etc.) shows unauthorized access in their own logs

In any of these cases: stop using the toolkit, contact Vercel support, contact the affected vendor, and consider engaging a third-party incident response firm.
