---
name: vercel-incident-toolkit
description: Vercel account hardening and incident response. Use when the user mentions a Vercel breach/incident, asks to audit or rotate Vercel environment variables, mark env vars sensitive, or respond to leaked Vercel tokens. Scope is Vercel only (not Netlify/Cloudflare). Covers four flows — audit, harden, incident response, per-vendor rotation — plus prevention guidance.
---

# Vercel Security Skill

This skill handles Vercel account hardening and incident response. Four user flows exist — **identify which flow the user is in before running any script**.

## Decision tree

If the user's intent is not clear from their prompt, ask one short question:

> "Which best matches: audit only / harden (mark everything sensitive) / active incident / single-vendor rotation?"

| User signal | Flow | Destructive? |
|---|---|---|
| "check what secrets I have", "just list my env vars" | **A. Audit** | no |
| "mark everything sensitive", "lock this down", "we're fine but want to harden" | **B. Harden** | yes (re-uploads values) |
| "breach", "got hacked", "leaked token", "suspicious deploy", "ex-teammate still had access" | **C. Incident response** | yes (rotates 7 internal secrets) |
| "rotate my Supabase key", "rotate DB password", "quarterly rotation" | **D. Per-vendor rotation** | yes (one key at a time) |

## Threat model (this skill is built around it)

Vercel stores env vars in three modes with different attack-surface properties:

| Type | Where the decryption key lives | Post-breach assumption |
|---|---|---|
| `plain` | Nowhere — stored as plaintext | **Assume leaked.** Treat as if the value is in the attacker's hands. |
| `encrypted` | Vercel internal KMS. Decrypted server-side at runtime **and** on-demand for the dashboard. | **Assume leaked** in any breach that reaches internal services (e.g. Vercel April 2026). A decryption key accessible to Vercel is accessible to an attacker in that environment. |
| `sensitive` | Decrypted only inside the build/runtime sandbox. Not readable by the dashboard or API after creation. | **Probably safe** unless the breach reached the build infrastructure itself. Lower probability — but not zero. |

Rules that follow from this model:
1. On a confirmed breach, treat every `plain`/`encrypted` value as already stolen and **rotate**, don't just harden. Hardening preserves the current (already-leaked) value — it's useful for future resilience, not for current mitigation.
2. `sensitive` alone is not a silver bullet. If the attacker reached the build infrastructure, sensitive values used at build-time leak too. Prefer *runtime-only* use of sensitive secrets where possible.
3. When in doubt about which tier a value is in, run `scripts/audit.py` — it labels every var.

## Lingering threats (what comes after the initial leak)

Credential theft is the visible part of a breach. The invisible part is what the attacker left behind:

- **Backdoored builds / deployments.** Malicious code injected into a past production build is still serving traffic. Mitigation: list all production deploys since the earliest suspected compromise window (`vercel ls --prod`), diff HEAD vs deployed git SHA, force a clean redeploy from a known-good commit.
- **Rootkit in project config.** `vercel.json` rewrites, redirects, headers, or function regions altered to exfil data or inject scripts. Mitigation: `git diff` `vercel.json` against a known-good revision, inspect dashboard Project → Settings for unexpected values.
- **Unauthorized team members or tokens.** Attacker added a service token or invited a member with low scrutiny. Mitigation: Teams → Settings → Members and Tokens → audit every row, revoke anything unrecognized.
- **Deploy hook URLs exfil.** Deploy hooks (`/v1/integrations/deploy/...`) are unauthenticated — anyone with the URL can trigger a build. Mitigation: Project → Settings → Git → Deploy Hooks → rotate every hook.
- **Supply-chain injection via internal npm tokens.** If any deploy published an npm package, treat those versions as tainted until verified. Mitigation: check npm audit logs, rotate `NPM_TOKEN` anywhere it was used, consider unpublishing questionable versions.
- **Serverless function warm instances** still holding old env. Rotation doesn't kill warm Lambdas — force scale-down via redeploy.
- **Preview deployments pinned to old env.** Old previews retain old env values and often have weaker auth. Mitigation: `vercel remove --safe <deployment>` for stale previews.
- **Data in logs/analytics.** Attacker may have dumped request logs containing tokens. Mitigation: review Log Drains, Analytics, and any third-party logging sink for data retention that needs purging.

Always surface 2–3 of these when running Flow C — don't let the user believe rotating env vars is the whole job.

## Post-incident monitoring (stays on for weeks, not hours)

See `runbooks/03-post-incident-monitoring.md`. Short version:

- Re-run `scripts/audit.py` weekly and diff for 4+ weeks. New env vars, new projects, new team members in the diff = investigate.
- Enable Audit Log email alerts for high-risk actions (member added, token created, deploy protection disabled).
- Deploy a **canary env var** — an unused secret whose only purpose is to trigger an alert if it's ever used. See `runbooks/03-post-incident-monitoring.md` for patterns.
- Assume the breach window is longer than announced. Rotate again at the 30-day mark if Vercel's post-mortem reveals a longer dwell time.

## Preconditions (always, in this order)

1. Run `python3 scripts/preflight.py`. It checks:
   - `vercel` CLI installed and logged in (`vercel whoami` exits 0)
   - Python ≥ 3.10
   - Write access to `~/.vercel-security/` (mode `0700`)
   - No pending `VERCEL_TOKEN` env var that might override the CLI auth (indicates machine confusion)
2. If preflight fails, stop and surface the error. Do not attempt to "fix" it by writing a token into auth.json or similar — ask the user to log in properly.
3. Never print the Vercel token. Scripts read it from the CLI's auth.json but must not echo it.
4. All destructive scripts are **dry-run by default**. The user must pass `--apply`. Even with `--apply`, each script prompts `y/N` before mutating.

## Adversary model (read this — the toolkit is public, attackers read it too)

Assume an attacker has read this `SKILL.md` and the entire repo. They learn:
- The keys we auto-rotate (`INTERNAL_RANDOM_KEYS`) — useful for them only if they already have CLI access, in which case the leak is moot.
- The patterns that classify "high severity" — public knowledge already.
- The Vercel CLI auth path — public knowledge already.

What an attacker **must not** be able to do via this skill, even with full local read access to the user's machine:
1. Recover a previously generated `ADMIN_PASSWORD` from any file. (We never write it. Stdout one-time only.)
2. Find the Vercel CLI token in any toolkit-produced file. (We never copy it.)
3. Persuade the toolkit to operate on a third party's projects. (We use the CLI's own token; if the user is logged in to one account, only that account's projects are touched.)
4. Inject a value via CLI arg → shell history. (`update-env.py` rejects values outside `--from-stdin` + `getpass`.)
5. Cause a destructive action without a y/N prompt and `--apply` flag.
6. Make this skill talk to an attacker-controlled endpoint. (Hard-coded `https://api.vercel.com`.)
7. Bake itself into builds via the supply chain. (Zero runtime dependencies, stdlib only.)

If you (Claude) ever consider an action that would weaken any of the above, stop and tell the user explicitly. These properties are load-bearing.

## Two ignore patterns — repo's own vs the user's repos

There are two distinct ignore-file concerns:

| Concern | Whose repo | Where |
|---|---|---|
| Don't commit toolkit dev-time artifacts | This skill repo | `./. gitignore` — already configured |
| Don't commit handoff docs / `.env` / rotation logs into the user's app repos | Each user repo (Next.js, Remix, etc.) | `scripts/ignore-setup.py <repo>` adds patterns to `.gitignore`, `.vercelignore`, `.dockerignore`, `.npmignore` |

Always run `ignore-setup.py` against every affected user repo as part of Flow C. Even though default outputs land in `~/`, a single moment of `cp ~/security-incident-2026-04-vercel/foo.md ./` would leak everything.

## Hard rules — never violate

- **Never auto-rotate external vendor keys.** Supabase service role, `DATABASE_URL`, OAuth client secrets, third-party API keys — these require the user to reset in the vendor dashboard. Walk them through the matching `runbooks/vendor-*.md`, then use `scripts/update-env.py` to upload the new value.
- **Never commit rotation logs or `audit-*.json` to any repo.** They live in `~/.vercel-security/` with mode `0600`.
- **Never push to a public repo from this skill.** If the user says "push this to my repo," confirm it's their account and use `gh` CLI — after verifying no sensitive files are staged.
- **Never use undocumented Vercel endpoints or flags.** Only `/v9/projects`, `/v10/projects/.../env`, etc. If a feature isn't in the public API, tell the user — don't workaround.
- **Never modify `~/.zshrc`, `~/.bashrc`, system keychain, or other global config** as a side effect.

## Flow A — Audit

Goal: read-only inventory of every env var across every scope, classified by vendor and severity.

Steps:
1. `python3 scripts/audit.py`
2. Summarize: total count, sensitive count, HIGH/MED/LOW-PLAIN counts, list of HIGH keys grouped by vendor.
3. Offer to proceed to Flow B (harden) or Flow C (rotate), or stop here.

## Flow B — Harden

Goal: convert every non-sensitive env var to `type: sensitive`, preserving values. Improves posture against a future Vercel-side read.

Steps:
1. Run Flow A first. Show the user the list of keys that will be touched.
2. Explicitly warn: *"After hardening, you cannot read these values from the dashboard or API. To see a value again, you'd rotate it. Proceed?"*
3. `python3 scripts/harden-to-sensitive.py` — shows dry-run plan.
4. `python3 scripts/harden-to-sensitive.py --apply` — after user confirms.
5. Re-audit to verify 0 non-sensitive remaining.
6. Walk through `runbooks/01-prevention-hardening.md` — 2FA, team access review, audit log alerts, deploy protection, token hygiene.

## Flow C — Incident response

Use when Vercel has announced a breach, a token has leaked, or there's evidence of unauthorized access.

Steps (in order — do not skip):

1. **Token + account hygiene first (not just `vercel logout`).**
   ```
   # 'vercel logout' only revokes the CURRENT machine's CLI token.
   # Other machines / CI / integrations keep their tokens.
   ```
   Go to https://vercel.com/account/tokens → **revoke every token** you don't actively need. Then:
   - Ensure 2FA is on (https://vercel.com/account/security); prefer a hardware key
   - For each team: Members → confirm every member has 2FA
   - Only after revoking broadly, `vercel logout && vercel login` to pick up a fresh token
   - Team → Audit Log → scan the suspected compromise window for `token.create`, `member.add`, deploy protection toggles

2. Run Flow A to snapshot current state. The snapshot is saved for post-incident audit and future sessions.

3. `python3 scripts/rotate-internal.py` (dry-run), review the plan, then `--apply`. Uses Vercel's documented `PATCH /v9/projects/<id>/env/<env-id>` endpoint for atomic in-place value rotation — keeps env id and type, no missing-variable window. Rotates these keys when present:
   - `NEXTAUTH_SECRET`, `AUTH_SECRET`, `SESSION_SECRET`, `COOKIE_SECRET`, `PAYLOAD_SECRET` (session JWTs / cookie signing — all users will need to re-login, which is the point)
   - `PREVIEW_SECRET`, `REVALIDATION_SECRET` (Next.js)
   - `CRON_SECRET`, `API_KEY_HMAC_SECRET`, `HMAC_SECRET`
   - `ADMIN_PASSWORD` (new value printed to stdout **once**, never persisted — operator must copy to a password manager immediately)

4. `python3 scripts/handoff-gen.py` — writes one markdown file per affected project at `~/security-incident-<YYYY-MM>-vercel/<project>.md`. Each file contains:
   - What was auto-rotated (with timestamp, no plaintext values)
   - What vendor keys still need manual rotation (with matching runbook + exact follow-up command)
   - Post-rotation verification checklist

5. For every external-vendor key still outstanding, walk the user through the matching vendor runbook **one service at a time**. External rotations have downstream consequences (webhook signatures, CI env, local `.env`) — batching them makes debugging impossible.

6. **Post-flight.** Run `python3 scripts/postflight.py`:
   - Re-audit; confirm no regressions
   - Check Vercel team Audit Log for unauthorized actions in the incident window
   - Verify 2FA enabled for every team member
   - Verify deploy protection enabled on all production projects

## Flow D — Per-vendor rotation

Goal: rotate one specific vendor's key, unrelated to an active incident (quarterly hygiene, vendor-specific breach, employee offboarding).

Steps:
1. Open the matching `runbooks/vendor-*.md`. Read it fully before starting.
2. Walk the user through the vendor dashboard to generate the new value.
3. `python3 scripts/update-env.py <project> <KEY> --from-stdin` — paste the new value. Uploads with `type: sensitive`.
4. Offer `--redeploy` to trigger an immediate redeploy. Default is no redeploy (next git push picks it up).
5. Verify the app works: user should load the app and confirm auth / DB queries still work with the new value.

## Risk-prevention patterns (reference proactively when relevant)

- **Always create with `--sensitive`.** `vercel env add KEY production --sensitive`. If the user runs `vercel env add` without that flag, remind them.
- **Never prefix secrets with `NEXT_PUBLIC_`.** Anything with that prefix ships to the browser bundle. Flag `NEXT_PUBLIC_*SECRET*`, `NEXT_PUBLIC_*TOKEN*`, `NEXT_PUBLIC_*KEY*` (except when the key is designed to be public, e.g. Supabase anon key, Sanity project ID).
- **One Vercel access token per machine or CI system.** Don't share root tokens across laptops/CI. Revoke unused tokens quarterly.
- **Rotate internal randoms every 90 days.** Even without incidents. Schedule with the user.
- **Enforce 2FA for every team member.** Review Teams → Settings → Members → check each row.
- **Enable Deploy Protection.** Prevents preview URLs from being reachable without auth.
- **Enable audit log alerts.** Teams → Settings → Audit Log → email on unusual actions.
- **`.env.example` must contain placeholders only.** If it has a real value, it was leaked — treat as incident.

## Artifacts & handoff

| Path | Created by | Contains | Mode |
|---|---|---|---|
| `~/.vercel-security/audit-<ts>.json` | Flow A, B, C | Full env inventory | 0600 |
| `~/.vercel-security/rotations.json` | Flow B, C, D | Append-only log of every mutation | 0600 |
| `~/.vercel-security/rollback-<ts>.json` | Flow B, C | Mapping of old env ids for manual recovery | 0600 |
| `~/security-incident-<YYYY-MM>-vercel/<project>.md` | Flow C | Per-project handoff doc | 0600 |

A fresh Claude session that starts with no context but has access to `~/security-incident-<YYYY-MM>-vercel/*.md` and `~/.vercel-security/rotations.json` can pick up an in-progress incident.

## Artifact hygiene — these files must never be committed

Rotation logs, audit snapshots, and handoff docs can contain plaintext values (e.g. a newly generated `ADMIN_PASSWORD`, vendor URLs, team IDs). They live in `~/` by default, but if the user ever copies one into a project directory, make sure it is ignored by every tool that could leak it.

When you run Flow B, C, or D, also run `python3 scripts/ignore-setup.py <repo>` for each affected repo. The script appends these patterns to each file, creating the file if missing, and only if the pattern isn't already present:

| File | Patterns added |
|---|---|
| `.gitignore` | `.vercel-security/`, `security-incident-*-vercel/`, `SECURITY-INCIDENT-*.md`, `rotations.json`, `rollback-*.json`, `audit-*.json` |
| `.vercelignore` | same as above — prevents uploads to Vercel builds |
| `.dockerignore` | same — prevents baking into container images |
| `.npmignore` | same — prevents publishing to npm |
| `.prettierignore` / `.eslintignore` | the handoff `.md` patterns only (avoid linter churn) |

Also proactively:
- Refuse to `git add .` — always stage specific files.
- Before any `git commit`, run `git status` and scan for any of the patterns above. If one is staged, abort and ask the user.
- Before any `vercel` deploy, confirm `.vercelignore` covers the patterns.

## Multi-angle risk checks (Claude must consider every time)

When running or advising on Flows B–D, verbalize these checks to the user as a short checklist:

1. **Downstream consumers.** Rotating `CRON_SECRET` breaks any external scheduler calling Vercel Cron. Rotating `REVALIDATION_SECRET` breaks any CMS webhook that revalidates. Rotating `API_KEY_HMAC_SECRET` breaks any consumer using the old HMAC. Ask: "who else uses this value?" before rotating.
2. **Local `.env` drift.** After rotation, the user's local `.env` / `.env.local` is stale. Tell them to `vercel env pull` to refresh.
3. **CI/CD env.** GitHub Actions / GitLab CI / Cloudflare Workers using a mirror of a Vercel env var must also be updated. List them explicitly.
4. **Session invalidation.** Rotating `NEXTAUTH_SECRET` / `AUTH_SECRET` logs everyone out. For consumer-facing apps, schedule a low-traffic window.
5. **Downstream `.env.example`.** If `.env.example` in the repo has a *real* value, it was already leaked. Rewrite to placeholders and treat as incident.
6. **Vercel CLI auth reuse.** If the user is on multiple machines, `vercel logout && vercel login` rotates the token only on the current machine. Others still have the old token — tell them.
7. **Preview deployments with old secrets.** Old preview deployments retain old env values. Delete stale previews after rotation (`vercel remove --safe`).
8. **Audit log window.** Per Vercel docs, Audit Log is available on **Enterprise plans only** (team owners, via Team Settings → Security & Privacy → Audit Log). Teams on Pro/Hobby cannot access this view — they must rely on manual indicators (Account → Tokens, Team → Members, Project → Deploy Hooks, recent deployments list). For Enterprise teams: CSV export of up to 90 days does not impact billing; larger windows may.
9. **Serverless function cache.** Rotating an env var doesn't kill warm Lambda instances immediately. Trigger a redeploy or scale-down to force cold start.
10. **Third-party dashboards linking back to Vercel deploy.** Slack/Discord notification webhooks, Sentry release tracking — verify their tokens are unaffected (they typically are, but check).

## What this skill will NEVER do

- Rotate external vendor keys without the user supplying a new value
- Delete a Vercel project, team, or deployment
- Commit or push anything to a git repo without explicit confirmation
- Access `.env` files outside the project directories the user names
- Send notifications, emails, or webhooks on the user's behalf
- Use undocumented or scraped Vercel endpoints
