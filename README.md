# vercel-incident-toolkit

**English** · [한국어](README.ko.md) · [日本語](README.ja.md) · [简体中文](README.zh-Hans.md)

> ⚠️ **Disclaimer.** Not an official tool. Not a complete answer. Not a substitute for thinking. A **guideline skill** — a structured reference with *optional* CLI automation — written by one engineer in the hours after the [Vercel April 2026 security incident](https://vercel.com/kb/bulletin/vercel-april-2026-security-incident). Read every script before `--apply`. Use at your own risk. Authoritative guidance is always the official Vercel docs (linked throughout).

> 🤖 **Don't hand this skill to an AI and walk away.** This toolkit operates on your live Vercel account. Before any `--apply`, audit the scripts — by yourself, or *alongside* an AI that explains each script, justifies its plan, and diffs your copy against the upstream `main`. "The AI said it's fine" is a checkpoint, not a green light. Every destructive action is your decision.

A **guideline-first toolkit + Claude Code skill** for **Vercel account hardening and incident response**. Think of it as a checklist you can execute by hand *or* let scripts execute for you — your choice at each step. Vercel-only scope. No runtime dependencies.

## Scope — what this touches

- **Your entire Vercel account, via the local `vercel` CLI authentication.** Enumerates every team you're in and every project in those teams through the documented Vercel REST API. Not limited to any specific repo or local directory.
- **Does NOT scan your local git repositories.** Local paths are only touched when *you* explicitly pass a path to `scripts/ignore-setup.py`.
- **Does NOT talk to any host other than `api.vercel.com`.**
- **Does NOT modify shell rc files, system keychain, or global config.**

## Two ways to use it — pick per-step

| Mode | How | When |
|---|---|---|
| **Automated (CLI)** | Run the scripts with `--apply` | You trust the dry-run output and want the toolkit to execute the mutation |
| **Manual (reference)** | Run `scripts/audit.py` (always read-only) + `scripts/handoff-gen.py`, then do everything else by hand in the Vercel dashboard and vendor dashboards | You want the toolkit to tell you *what* needs to change but want to make every change yourself |

You don't have to pick one mode for the whole incident — mix per step. Common choice: automated for the internal-random rotation in Flow C, manual for every external vendor rotation. All destructive scripts are **dry-run by default** and prompt `y/N` before any change.

---

## Vercel April 2026 — first-response checklist

Aligned with Vercel's official recommendation ("review environment variables and use the sensitive environment variable feature"). This toolkit automates the review and adds rotation + handoff docs on top.

### Step 0 — Token & account hygiene FIRST (don't skip)

`vercel logout && vercel login` is **not enough on its own**. During a breach:

1. Go to [vercel.com/account/tokens](https://vercel.com/account/tokens) → **revoke every token** you don't actively need. `vercel logout` only revokes the current machine's CLI token; other machines, CI runners, and integrations hold their own.
2. [Enable 2FA](https://vercel.com/account/security) if not already. Prefer a hardware key over TOTP.
3. For each team: Team → Settings → Members → verify every member has 2FA. Remove ex-teammates/contractors.
4. `vercel logout && vercel login` on this machine to pick up a fresh, known-clean token.
5. Team → Audit Log → scan the suspected compromise window for `token.create`, `member.add`, `role.change`, `project.create`, deploy-protection toggles.

Only after this, run the toolkit.

### Step 1 — Audit & rotate internal secrets (toolkit)

```bash
git clone https://github.com/subinium/vercel-incident-toolkit
cd vercel-incident-toolkit
python3 scripts/preflight.py                 # environment checks
python3 scripts/audit.py                     # read-only inventory
python3 scripts/rotate-internal.py           # dry-run — shows the plan
python3 scripts/rotate-internal.py --apply   # actually rotates
python3 scripts/handoff-gen.py               # per-project next-step docs
```

After step 1, open `~/security-incident-<YYYY-MM>-vercel/` — one markdown file per affected project, listing vendor keys that still need manual rotation with the exact follow-up commands.

### Step 2 — Rotate external vendor keys (manual, sequential)

Vendor keys (Supabase service role, `DATABASE_URL`, OAuth client secrets, third-party APIs) are **never auto-rotated**. Follow Vercel's [official rotation pattern](https://vercel.com/docs/environment-variables/rotating-secrets):

1. Generate new credential in the vendor's dashboard (do **not** invalidate the old one yet).
2. Upload the new value to Vercel: `python3 scripts/update-env.py <project> <KEY> --from-stdin --apply`.
3. Redeploy the Vercel project and verify it works.
4. **Only then** invalidate the old credential in the vendor's dashboard.

Per-vendor runbooks: [`runbooks/vendor-*.md`](runbooks/). One vendor at a time — never batch.

### Step 3 — Harden (optional, after rotation)

```bash
python3 scripts/harden-to-sensitive.py --apply
```

Converts every non-sensitive env var to `sensitive` type per Vercel's [sensitive env var docs](https://vercel.com/docs/environment-variables/sensitive-environment-variables). Post-hardening, values can't be read back from the dashboard or API — to see one again, rotate it.

> **Vercel official constraint:** sensitive type is only available in **production** and **preview** targets — the development target can't be marked sensitive. The toolkit falls back to `encrypted` for development targets automatically.

### Step 4 — Post-rotation (see [`runbooks/04-after-rotation.md`](runbooks/04-after-rotation.md))

- `vercel env pull` in each project to refresh local `.env`
- `vercel --prod` per project to force cold-start (drops warm instances holding old env)
- Update CI/CD secret mirrors (GitHub Actions, etc.)
- Rotate every [Deploy Hook](https://vercel.com/docs/deployments/deploy-hooks) URL
- Weekly `scripts/audit.py` for 30 days; diff for unexpected new env vars or projects

---

## Threat model — aligned with Vercel's architecture

Per Vercel's [sensitive environment variables docs](https://vercel.com/docs/environment-variables/sensitive-environment-variables):

| Type | Where the decryption key lives | Post-breach assumption |
|---|---|---|
| `plain` | Nowhere — stored as plaintext | **Assume leaked** |
| `encrypted` | Vercel internal KMS — decrypted server-side for the dashboard and runtime | **Assume leaked** in a breach reaching internal systems |
| `sensitive` | Restricted path — *"non-readable once created"*, not returned by the dashboard or API | **Probably survived** unless the breach reached the build/runtime sandbox |

Rules that follow:
1. Rotation > hardening for any value leaked. Hardening preserves a value that is already compromised.
2. Sensitive is not magical — build-time access still exposes values if build infra is breached.
3. Per Vercel docs, "to mark an existing environment variable as sensitive, remove and re-add it with the Sensitive option enabled." Type upgrades are delete+create, not in-place edits.

---

## Is this toolkit the right fit?

**Good fit:**
- You run a handful of Next.js / Remix / SvelteKit / Nuxt apps on Vercel
- You want a repeatable first response in minutes, not hours
- You use common auth (Auth.js / NextAuth / Clerk / Supabase Auth) and DB (Supabase / Neon / Postgres)

**Partial fit:**
- Non-JS stacks — Flow A (audit) still works; Flow C (auto-rotate) only handles the listed keys. Use `--include` to add your framework's known-safe randoms.
- Custom JWE / field-level encryption / rotation-dependent session designs — do those manually.

**Not a fit:**
- Compliance artifacts (SOC 2, ISO 27001). This is an operator playbook, not evidence.
- Change-advisory-board processes. Every mutation here is immediate.

**What the toolkit does NOT catch (do these manually):**
- Malicious code baked into a past production deployment → `vercel ls --prod` + git SHA diff
- Unauthorized team members added via social engineering → Audit Log review
- Tokens on other devices you forgot about → revoke all tokens centrally
- Secondary compromise of linked services → per-vendor audit logs

When in doubt, treat the toolkit's output as a verification checklist, not a claim of completion.

---

## The four flows

### A. Audit — `scripts/audit.py`
Enumerates every project in every scope (personal + teams), lists every env var, classifies each by severity (`OK` sensitive / `HIGH` high-risk encrypted / `MED` generic encrypted / `LOW-PLAIN` plaintext). Read-only. Writes `~/.vercel-security/audit-<timestamp>.json`.

### B. Harden — `scripts/harden-to-sensitive.py`
Re-uploads every non-sensitive env var with `type: sensitive` (same value), per Vercel's [sensitive env var docs](https://vercel.com/docs/environment-variables/sensitive-environment-variables). Uses `vercel env pull` for plaintext, then documented `DELETE` + `POST` endpoints. Skips `NEXT_PUBLIC_*` (public by design). Falls back to `encrypted` for development targets (Vercel constraint). Dry-run by default.

### C. Incident — `scripts/rotate-internal.py` + `handoff-gen.py`

Rotates known-random internal secrets if present. Uses Vercel's `PATCH /v9/projects/.../env/<id>` endpoint for atomic value rotation (keeps type, no delete-then-create gap). Default list:

| Key | What it guards |
|---|---|
| `NEXTAUTH_SECRET` / `AUTH_SECRET` | NextAuth / Auth.js session JWTs |
| `SESSION_SECRET` / `COOKIE_SECRET` | Remix / Express / Hono / Fastify session signing |
| `PAYLOAD_SECRET` | PayloadCMS |
| `PREVIEW_SECRET` / `REVALIDATION_SECRET` | Next.js preview / on-demand ISR |
| `CRON_SECRET` | Vercel Cron authorization |
| `API_KEY_HMAC_SECRET` / `HMAC_SECRET` | HMAC signatures for internal APIs |
| `ADMIN_PASSWORD` | Simple admin — **new value printed to stdout once, never persisted** |

Pass `--include KEY1,KEY2` to extend. The script **refuses** anything matching `NEVER_ROTATE_PATTERNS` (at-rest encryption, vendor secrets, long-lived JWT signing keys — rotating these breaks stateful data).

`handoff-gen.py` writes per-project markdown at `~/security-incident-<YYYY-MM>-vercel/<project>.md` with exact vendor-dashboard steps. No plaintext values included.

### D. Vendor rotation — `scripts/update-env.py`
After you rotate a key in a vendor dashboard:
```bash
python3 scripts/update-env.py <project> <KEY> --from-stdin --apply
```
Follows Vercel's [safe rotation pattern](https://vercel.com/docs/environment-variables/rotating-secrets) — uploads the new value (as `sensitive` where allowed, `encrypted` for development target), optionally triggers a redeploy via `--redeploy`, and logs to `~/.vercel-security/rotations.json` (no plaintext).

**Order matters:** upload the new value to Vercel *before* you invalidate the old one in the vendor's dashboard. Per Vercel docs: *"The key to safe rotation is updating Vercel before you invalidate the old credential."*

---

## Two `.gitignore` concerns — don't confuse them

This toolkit repo's `.gitignore` prevents contributors from committing toolkit-dev artifacts.

Your **Vercel-deployed app repos** also need ignore patterns — so a stray `vercel env pull` or handoff doc never lands in git. Run once per app repo:

```bash
python3 scripts/ignore-setup.py /path/to/your/app-repo
```

Appends patterns to `.gitignore`, `.vercelignore`, `.dockerignore`, `.npmignore`. Idempotent.

Default toolkit outputs land in `~/.vercel-security/` and `~/security-incident-*-vercel/` — outside every repo. The ignore patterns are belt-and-suspenders.

---

## Supply chain & adversary model

Assume an attacker has read every line of this repo.

**What they learn:** key-name patterns we classify, the path to your local Vercel CLI auth file, the set of Vercel API endpoints we use. All of these are also in Vercel's public docs.

**What they do not learn:** your token (read at runtime only, never embedded), your project names/IDs, any rotation log, any plaintext value.

**Structural safety properties of the scripts:**
- Accept secret values only via `getpass` (never CLI args — would land in shell history)
- Never print or log the Vercel CLI token, even on error
- Never persist any plaintext rotation value (including `ADMIN_PASSWORD` — stdout once, then dropped)
- Read/write only within `~/.vercel-security/`, `~/security-incident-*-vercel/`, and explicitly named target-repo paths
- Make no network call to anything other than `api.vercel.com`
- Retry idempotent API calls on 429/5xx with exponential backoff; never retry 4xx rejections

**Supply chain:**
- Pure Python standard library. No `requirements.txt`, no npm, no external imports. If you see one in your copy, it has been tampered with.
- Tag releases for pinning: `git checkout v0.1.0`.
- Fork → audit the diff → run. Don't `git clone main` from an unknown fork.

If you fork and weaken any of these properties, document the change loudly at the top of your README. Users should not need to read the diff to know the safety properties changed.

---

## Runbooks

Process:
- [`00-incident-response.md`](runbooks/00-incident-response.md) — minute-by-minute playbook
- [`01-prevention-hardening.md`](runbooks/01-prevention-hardening.md) — Vercel security settings you should already have on (Git Fork Protection, Deploy Protection, Build Logs Protection, Enforce Sensitive policy, OIDC for AWS)
- [`02-common-mistakes.md`](runbooks/02-common-mistakes.md) — near-misses, what not to do
- [`03-post-incident-monitoring.md`](runbooks/03-post-incident-monitoring.md) — weekly audits, canaries, when to close
- [`04-after-rotation.md`](runbooks/04-after-rotation.md) — what "done" actually means after the toolkit finishes

Per-vendor:
- [Supabase](runbooks/vendor-supabase.md)
- [Google OAuth](runbooks/vendor-google-oauth.md)
- [Neon / Postgres](runbooks/vendor-neon.md)
- [Generic third-party API](runbooks/vendor-generic.md)

---

## Authoritative references (official + verified)

Vercel official (always trust these over anything else, including this README):
- [Vercel April 2026 security incident — KB bulletin](https://vercel.com/kb/bulletin/vercel-april-2026-security-incident)
- [Rotating environment variables — official pattern](https://vercel.com/docs/environment-variables/rotating-secrets)
- [Sensitive environment variables](https://vercel.com/docs/environment-variables/sensitive-environment-variables)
- [Environment variables (overview)](https://vercel.com/docs/environment-variables)
- [Project security settings](https://vercel.com/docs/project-configuration/security-settings)
- [Tokens](https://vercel.com/docs/sign-in-with-vercel/tokens)
- [Deploy Protection](https://vercel.com/docs/deployment-protection)
- [OIDC Federation](https://vercel.com/docs/oidc) — move off long-lived AWS/GCP keys to short-lived tokens

Verified third-party:
- [GitGuardian — Remediating Vercel API access token leaks](https://www.gitguardian.com/remediation/vercel-api-access-token)

This README intentionally avoids citing unverified blog posts. If a source isn't above, it wasn't cross-checked enough to recommend.

---

## License

MIT.
