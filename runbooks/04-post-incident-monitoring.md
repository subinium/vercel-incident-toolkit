# Runbook 04 — Post-incident monitoring

Rotation closes the immediate hole. Lingering threats — backdoors, persistent footholds, secondary credentials — are harder.

## Daily, for two weeks after rotation

- Run `python3 scripts/audit.py` and diff against the previous day's snapshot. New env vars or projects appearing without your action = investigate immediately.
- Skim Vercel team Audit Log for: member added, token created, deploy protection toggled, new project, role change.
- Check `vercel ls --prod` for deployments you didn't trigger (compare to git commit log).

## Weekly, for one month after rotation

- Diff `vercel.json` against last known-good revision in every project.
- Verify Deploy Hooks list has not grown.
- Verify team member list has not grown.
- For projects publishing npm packages from CI: check `npm` audit log for unexpected publishes.
- For projects with external webhooks: check the consumer's logs for traffic in unusual time windows.

## One-time, ASAP

- Export the Vercel Audit Log covering the entire incident window (initial breach disclosure → rotation completion). Save to `~/.vercel-security/audit-log-export-<YYYY-MM>.json`. Pro tier retains 90 days only.
- Force a fresh production redeploy on every project from a known-good commit. This drops any warm serverless instance still holding old env values, and overwrites any tampered build artifact.
- Inspect every Vercel integration (Slack, GitHub, Sentry, etc.) — verify token scopes, revoke unused.

## Optional: canary tokens

A canary token is a fake credential whose only purpose is to alert when used. Add one to every project as a tripwire.

Pattern:
1. Generate a unique-looking token: `secrets.token_urlsafe(32)` prefixed with something distinctive like `CANARY_DO_NOT_USE_`.
2. Add to Vercel as `_CANARY_VALUE` (sensitive, production target).
3. In application code: never reference `_CANARY_VALUE`. Instead, set up an external monitor that polls a service expecting that token and alerts if it's ever seen in the wild.
4. Rotate canaries quarterly — same cadence as real secrets.

Free options for the alerting side: Thinkst Canary (commercial), a pre-shared HMAC verification webhook on a server you control, or a Cloudflare Worker that logs and Slacks any incoming request bearing the canary value.

## When can you stop watching closely?

When **all** of these are true:
- Vercel publishes a complete post-mortem and your impacted-customer status is confirmed (or definitively negative).
- 30 days of clean audit logs.
- All downstream consumers verified working with new values.
- No vendor-side anomalies (Supabase, Neon, etc.) in their own logs.

Continue with the prevention defaults in `runbooks/01-prevention-hardening.md` indefinitely.
