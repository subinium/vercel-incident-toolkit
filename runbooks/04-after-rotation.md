# Runbook 04 — After rotation: what "done" actually means

You ran `rotate-internal.py --apply` and the green checkmarks look great. You are **not** done. Rotation closes the front door. This runbook closes the rest of the house.

Order matters. Don't skip steps even if the previous one looked clean.

---

## Step 1 — Immediate (within 10 minutes of rotation)

### 1a. Save any `ADMIN_PASSWORD` you saw
The script printed it to stdout once. It is nowhere on disk. If you lose it, rerun `rotate-internal.py --apply` to get a new one (the current one becomes inaccessible — that's the safety tradeoff).

### 1b. Rotate your local Vercel CLI token
```bash
vercel logout && vercel login
```
Why: if your machine's auth.json was ever copied off (malware, backup sync, loaned device), the token in it still works. Logout revokes it.

### 1c. Confirm the rotation log is local-only
```bash
ls -la ~/.vercel-security/rotations.json
# should be -rw------- (0600)
# should NOT be in any repo
```

---

## Step 2 — Propagate (within 1 hour)

### 2a. Refresh every local clone
For every project that had a rotated key, in each developer's machine:
```bash
cd /path/to/project
vercel env pull
```
Old `.env` values will cause confusing "works locally, broken in prod" bugs. Force-refresh.

### 2b. Update CI/CD secret mirrors
If any rotated key is also stored in:
- GitHub Actions Secrets (Repository → Settings → Secrets and variables → Actions)
- GitLab CI variables
- CircleCI / Travis / Bitbucket Pipelines
- Cloudflare Workers env bindings
- Railway / Fly.io / Render env

…update each one. A CI job using the old value will fail on next push, often in ways that mask the real cause.

### 2c. Trigger a clean redeploy per project
Forces cold-start of all serverless functions, dropping any warm instance holding old env values:
```bash
cd /path/to/project
vercel --prod --yes
```
Or push an empty commit:
```bash
git commit --allow-empty -m "chore: force redeploy after key rotation"
git push
```

### 2d. Smoke test production
For every project: load the production URL, sign in, exercise the critical path that uses the rotated key. Specifically:
- If you rotated `NEXTAUTH_SECRET` / `AUTH_SECRET` / `SESSION_SECRET` → log in and verify session persists
- If you rotated a DB credential → hit an endpoint that queries the DB
- If you rotated `CRON_SECRET` → wait for the next cron tick, check the logs

---

## Step 3 — Rotate vendor keys (within 24 hours, one service at a time)

The toolkit **does not** rotate external vendor keys. Open `~/security-incident-<YYYY-MM>-vercel/<project>.md` for each affected project. Each file lists exactly which vendor keys need manual rotation, with the matching runbook.

Do them sequentially (not in parallel). For each:
1. Open the matching `runbooks/vendor-*.md`.
2. Rotate in the vendor's dashboard.
3. Upload: `python3 scripts/update-env.py <project> <KEY> --from-stdin --apply`.
4. Redeploy + smoke test.
5. Only then move to the next key.

**Why sequentially?** When something breaks, you need to know which rotation caused it. Batching makes debugging impossible.

---

## Step 4 — Audit log review (within 24 hours)

Per Vercel's official docs, **Audit Log is available on Enterprise plans only**. If you are on Enterprise:

1. Team Settings → Security & Privacy → **Audit Log** (owner role required).
2. Filter to the period between earliest suspected compromise and now.
3. **Export CSV** — the email link is valid for 24 hours. CSV windows up to 90 days do not impact billing; larger ranges may. Save the exported file locally as `~/.vercel-security/audit-log-<YYYY-MM>.csv` (mode `0600`).
4. Review every row for:
   - `team.member.added` / `team.member.deleted` / `team.member.role.updated`
   - `project.env_variable.created` / `.updated` / `.deleted` you didn't make
   - `project.password_protection.disabled` or `project.sso_protection.disabled`
   - `project.transfer.started` / `.completed`
   - `shared_env_variable.decrypted` — one of the strongest indicators of snooping
   - `deploy_hook.deduped` + any unusual deploy origins

Anything you can't attribute to a known teammate = escalate.

**If you are on Pro or Hobby (no Audit Log access):** you cannot do this step as a formal review, but you can do the following manually:
- Account → Tokens — list every token and revoke anything unrecognized
- Team → Members — verify every member and their role
- Per project → Settings → Git → Deploy Hooks — list and rotate unknown hooks
- Per project → Deployments — scan recent production deploys; compare deployed git SHA against your main branch
- Per project → Settings → Environment Variables — compare against your expected list; diff with the toolkit audit snapshot

---

## Step 5 — Close known lateral-movement paths (within 48 hours)

### 5a. Rotate Deploy Hooks
Project → Settings → Git → Deploy Hooks. Every URL there triggers a build without auth — anyone with the URL can deploy. Rotate them all.

### 5b. Revoke unused personal tokens
Account → Settings → Tokens. Revoke anything unrecognized, anything older than 90 days without a clear purpose, and anything tied to a device you no longer use.

### 5c. Review team members
Teams → Settings → Members. Remove:
- Ex-teammates still listed
- Contractors whose engagement ended
- Anyone without 2FA enabled

### 5d. Diff `vercel.json` per project
Compare each project's `vercel.json` against last known-good revision in git. Look for unexpected `rewrites`, `redirects`, `headers`, `functions` region changes.

### 5e. Inspect recent deploys
```bash
vercel ls --prod --cwd /path/to/project
```
For each production deploy since earliest compromise window: does the deployed git SHA match what you expect?

---

## Step 6 — Communicate (timing depends on your product)

If you rotated session-signing secrets (`NEXTAUTH_SECRET`, `AUTH_SECRET`, `SESSION_SECRET`):
- Every signed-in user has been logged out.
- For consumer-facing products: schedule a notice for a low-traffic window before rotating, or send a post-hoc email explaining the forced re-login.
- For internal tools: Slack/Discord announcement is enough.

If you rotated API-facing HMAC or webhook secrets:
- Every consumer using the old value is now broken until they update.
- List consumers in advance. Push new value to them synchronously.

---

## Step 7 — Monitor for 30 days (passive but mandatory)

See `runbooks/03-post-incident-monitoring.md`. Short version:
- Weekly `scripts/audit.py` diffs
- Enable Audit Log email alerts
- Optional: deploy canary env vars
- Re-rotate at 30 days if Vercel's post-mortem reveals a longer attacker dwell time than initially disclosed

---

## When can you close the ticket?

All of:
- [ ] Steps 1–6 fully done
- [ ] 30 days of clean audit logs post-rotation
- [ ] Vercel's formal post-mortem confirms your impacted-customer status
- [ ] No vendor-side anomalies (Supabase, Neon, etc.) in their own logs
- [ ] All downstream consumers confirmed working on new values
- [ ] Your team signed off on the close

Don't close early. "Rotation went smoothly" is not the same as "no lingering compromise."

---

## When to escalate instead

- Audit log shows actions you can't attribute
- A deploy published from an unrecognized commit
- A team member or token appears that nobody claims
- A vendor shows unauthorized access in their own logs
- Production behavior changed in ways the rotation alone shouldn't cause

Stop running the toolkit. Contact Vercel support. Contact each affected vendor. Consider engaging an external incident-response firm if the scope expands.
