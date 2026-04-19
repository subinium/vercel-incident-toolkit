# Runbook 01 — Prevention & hardening

Use this when there is **no active incident** and you want to reduce blast radius if one happens later.

## Account-level

- **2FA on every team member.** Teams → Settings → Members → review each row. No 2FA = remove or freeze.
- **SSO** if available on your plan. Forces all access through your IdP and gives you a single revoke point.
- **Audit Log alerts.** Teams → Settings → Audit Log → enable email on member added, token created, deploy protection disabled.
- **Rotate access tokens quarterly.** One token per machine / CI; revoke the rest. Account → Settings → Tokens.

## Project-level

- **Default to sensitive on every new env var.** CLI: `vercel env add KEY production --sensitive`. Dashboard: tick the "Sensitive" box.
- **Never prefix a secret with `NEXT_PUBLIC_`.** Anything with that prefix lands in the client bundle. The skill flags `NEXT_PUBLIC_*SECRET*`, `NEXT_PUBLIC_*TOKEN*`, `NEXT_PUBLIC_*KEY*` (except for known-public keys like Supabase anon, Sanity project ID).
- **Deploy Protection on previews.** Project → Settings → Deployment Protection → require auth. Without it, a leaked preview URL = unauthenticated access to a production-equivalent environment.
- **Rotate Deploy Hooks.** Anyone with the URL can trigger a build. Project → Settings → Git → Deploy Hooks.

## Repository hygiene

- Run `python3 scripts/ignore-setup.py /path/to/repo` to add toolkit-artifact ignore patterns to every project repo.
- `.env.example` must contain placeholders only. If it has a real value, that value is leaked — treat as incident.
- Do not commit `.vercel/project.json` if you share the repo with people who shouldn't have project access (it reveals the project ID).

## Operational defaults

- **Quarterly rotation** of internal-random secrets (NextAuth, AUTH, HMAC, CRON). Set a recurring calendar event. Run Flow C even without an incident — it's cheap.
- **Pull don't sync.** Use `vercel env pull` on each developer machine; never sync env files via Slack, email, or shared drives.
- **One Vercel account per device.** If you're on personal + work laptops, log in with the relevant account on each. `vercel logout` on a lost device only invalidates that machine's token; for true revocation use the dashboard.

## What good looks like

A monthly `python3 scripts/audit.py` should produce:
- 0 `LOW-PLAIN`
- 0 `HIGH` from non-sensitive keys (anything HIGH should be marked sensitive or rotated)
- All `MED` either marked sensitive or explicitly accepted as non-secret (`NEXT_PUBLIC_*`, URLs, feature flags)
