# Runbook 01 — Prevention & hardening

Use this during calm time to reduce blast radius if a breach happens later. Each item is backed by Vercel's official documentation — cited inline.

## Account & team

- **2FA on every team member.** Teams → Settings → Members → audit each row. Prefer hardware keys over TOTP.
- **Enforce Sensitive env var policy** (team owners). Settings → Security & Privacy → toggle *"Enforce Sensitive Environment Variables"*. After this, all new env vars in production + preview are sensitive by default. See [sensitive env var docs](https://vercel.com/docs/environment-variables/sensitive-environment-variables#environment-variables-policy).
- **Rotate access tokens quarterly.** One token per machine / CI; revoke the rest. Account → Settings → Tokens. [Token docs](https://vercel.com/docs/sign-in-with-vercel/tokens).
- **Audit Log alerts.** Teams → Settings → Audit Log → enable email on member added, token created, role changes, deploy protection toggled.

## Project security settings

(All under Project → Settings → Security — see [project security settings docs](https://vercel.com/docs/project-configuration/security-settings).)

- **Build logs and source protection — keep enabled.** Default-on; if disabled, anyone can reach `/_logs` and `/_src` on your deployments.
- **Git Fork Protection — keep enabled.** Without it, a PR from a repo fork can trigger a deploy and see production env vars. Default-on.
- **Deployment Retention Policy.** Old deployments retain old env values. Set a retention limit so stale deployments roll off rather than accumulate rotation debt. [Retention docs](https://vercel.com/docs/security/deployment-retention).
- **Vercel Support Code Visibility — keep disabled by default.** Only flip on when a Vercel support ticket requires it, then disable immediately after.

## Deployment Protection

[Deployment Protection docs](https://vercel.com/docs/deployment-protection). Prevents a leaked preview URL from being reached without auth.

- Enable at Project → Settings → Deployment Protection → *Vercel Authentication* (team-member-only) or *Password Protection* (shared link).
- For production + preview, configure separately. Preview deployments are the most common leak vector.

## Environment variable discipline

- **Default to sensitive.** `vercel env add KEY production --sensitive`. If the user creates via CLI without the flag, remind them.
- **Never prefix secrets with `NEXT_PUBLIC_`.** Anything with that prefix lands in the browser bundle. The toolkit's audit flags `NEXT_PUBLIC_*SECRET*`, `NEXT_PUBLIC_*TOKEN*`, `NEXT_PUBLIC_*KEY*` except keys that are designed to be public (Supabase anon, Sanity project ID).
- **Separate preview and production credentials.** Use staging API keys / DBs for preview — a leaked preview must not expose production data.
- **Sensitive cannot be applied to the development target.** Vercel constraint. Use encrypted there; use sensitive for production + preview only.

## Move off long-lived cloud keys — [OIDC Federation](https://vercel.com/docs/oidc)

If any project has `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` (or GCP equivalents) stored as env vars, migrate to OIDC:

- Vercel issues a short-lived OIDC token at build time
- Your cloud IAM verifies the token and grants scoped access for that build only
- No long-lived credential ever sits in your env vars
- Reduces blast radius to minutes, not "until you remember to rotate"

Supported for AWS, GCP, and Azure.

## Supply chain

- Pin dependencies (lockfile + `--frozen-lockfile` in CI). Vercel has written about the [Shai-Halud npm supply-chain campaign](https://vercel.com/changelog/shai-halud-supply-chain-campaign-expanded-impact-and-vercel-response); the toolkit itself has zero runtime dependencies for this reason.
- Never use `npm` / `pnpm` `preinstall` / `postinstall` scripts in build-time deps unless you've audited them. Vercel runs install scripts during builds.
- Review your `package.json` for any dep that executes during install or build.

## Repository hygiene

- `python3 scripts/ignore-setup.py /path/to/repo` — adds toolkit-artifact ignore patterns to `.gitignore`, `.vercelignore`, `.dockerignore`, `.npmignore`.
- `.env.example` must contain placeholders only. If it has a real value, that value is leaked — treat as incident.
- Never commit `.vercel/project.json` to a repo shared with people who shouldn't have project access (it reveals the project ID).

## Operational defaults

- **Quarterly rotation** of internal-random secrets. Set a recurring calendar event. `python3 scripts/rotate-internal.py --apply` — cheap, contained.
- **Pull, don't sync.** `vercel env pull` on each developer machine. Never ship env files via Slack / email / shared drives.
- **One Vercel account per device.** `vercel logout` on one device does not invalidate other devices' tokens. For true revocation, use the dashboard.

## What "hardened" looks like

A monthly `python3 scripts/audit.py` should show:
- 0 `LOW-PLAIN` anywhere
- 0 `HIGH` on non-sensitive storage — any high-risk key is either sensitive or has been rotated to a short-lived form
- Every `MED` either sensitive or explicitly accepted as non-secret (`NEXT_PUBLIC_*`, URLs, feature flags)
- Team settings: 2FA enforced, Enforce Sensitive policy on, Audit Log alerts on, Git Fork Protection on, Deployment Protection on for previews
