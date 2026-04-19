# vercel-incident-toolkit

> ⚠️ **Disclaimer.** This is not an official tool, not a complete answer, and not a substitute for thinking. It's a fast playbook one engineer wrote in the hours after the [Vercel April 2026 security incident](https://vercel.com/kb/bulletin/vercel-april-2026-security-incident) so other engineers can move quickly. Read every script before you run `--apply`. Use at your own risk.

A toolkit + Claude Code skill for **Vercel account hardening and incident response**. Vercel-only scope.

## Vercel April 2026 — do these now

If you got here because of the breach disclosure, the minimum five steps:

```bash
# 1. Rotate your local Vercel CLI token first
vercel logout && vercel login

# 2. Clone + run preflight
git clone https://github.com/subinium/vercel-incident-toolkit
cd vercel-incident-toolkit
python3 scripts/preflight.py

# 3. Snapshot every env var across every project (read-only)
python3 scripts/audit.py

# 4. Rotate internal-random secrets (NextAuth, AUTH, CRON, HMAC, ADMIN_PASSWORD, etc.)
python3 scripts/rotate-internal.py            # dry-run shows the plan
python3 scripts/rotate-internal.py --apply    # actually rotates

# 5. Generate per-project handoff docs for the manual vendor rotations
python3 scripts/handoff-gen.py
```

After step 5, open `~/security-incident-<YYYY-MM>-vercel/` for one markdown file per affected project — it lists which Supabase / Postgres / OAuth keys you still need to rotate in the vendor's dashboard, with exact next commands to upload the new value.

> Vendor keys (Supabase service role, `DATABASE_URL`, OAuth client secret, third-party APIs) are **never auto-rotated** by this toolkit — those require you to log into the vendor dashboard. Runbooks under [`runbooks/vendor-*.md`](runbooks/) walk you through each one.

## Why it exists

When Vercel disclosed that internal systems had been accessed, the recommended user action was to *"review environment variables and use the sensitive environment variable feature."* Most real accounts have dozens of projects, each with several env vars, scattered across personal + team scopes. Doing this by hand is slow, error-prone, and you can't tell from the dashboard which keys are already marked sensitive without clicking into every project.

This skill turns that into a repeatable workflow with four flows:

| Flow | When to use | Default mode |
|---|---|---|
| **A. Audit** | Anytime — what secrets do I have, where? | read-only |
| **B. Harden** | Calm time — mark everything `sensitive`, tighten team access | dry-run |
| **C. Incident** | Active breach — rotate internal secrets, draft handoff docs | dry-run |
| **D. Vendor rotation** | Quarterly or on vendor-specific incident | dry-run |

Every destructive script is **dry-run by default**. You have to pass `--apply` to actually change anything, and the script prompts for `y/N` before each batch. Every change is logged to a local file so you can roll back.

## Install

### As a Claude Code skill
```bash
git clone https://github.com/subinium/vercel-incident-toolkit ~/.claude/skills/vercel-incident-toolkit
```
Then just ask Claude Code something like *"audit my Vercel env vars"* or *"help me respond to the Vercel breach"* — it'll read `SKILL.md` and route to the right flow.

### Standalone (no Claude)
```bash
git clone https://github.com/subinium/vercel-incident-toolkit
cd vercel-incident-toolkit
python3 scripts/preflight.py          # verifies CLI login + env
python3 scripts/audit.py              # read-only inventory
python3 scripts/rotate-internal.py    # dry-run, shows plan
python3 scripts/rotate-internal.py --apply   # actually rotate
```

Requirements: Python ≥ 3.10, `vercel` CLI logged in (`vercel login`), no extra dependencies.

## The four flows (short version)

### A. Audit — `scripts/audit.py`
Enumerates every project in every scope (personal + teams), lists every env var, and classifies each by:
- severity: `OK` (sensitive), `HIGH` (encrypted + looks like a secret), `MED` (encrypted + generic), `LOW-PLAIN` (plaintext).
- vendor: Supabase, DATABASE_URL, Google OAuth, Auth.js secret, CryptoQuant, Stripe, Anthropic, OpenAI, etc.

Writes `~/.vercel-security/audit-<timestamp>.json`. Nothing is mutated.

### B. Harden — `scripts/harden-to-sensitive.py`
Re-uploads every non-sensitive env var with `type: sensitive` (same value). Uses `vercel env pull` for plaintext, then API `DELETE` + `POST` — no backdoor tricks. Skips `NEXT_PUBLIC_*` (public by design). Dry-run by default.

After this runs, values can no longer be read from the Vercel dashboard or API; to see them again, rotate. This is the point.

### C. Incident — `scripts/rotate-internal.py` + `handoff-gen.py`
Rotates seven known-random internal secrets if present:

| Key | What it guards |
|---|---|
| `NEXTAUTH_SECRET` / `AUTH_SECRET` | NextAuth / Auth.js session JWTs |
| `PREVIEW_SECRET` / `REVALIDATION_SECRET` | Next.js preview mode / on-demand ISR |
| `CRON_SECRET` | Vercel Cron authorization header |
| `API_KEY_HMAC_SECRET` | HMAC signatures for internal APIs |
| `ADMIN_PASSWORD` | Simple admin logins (new value is saved locally so you can retrieve it) |

External vendor keys (Supabase service role, DATABASE_URL, OAuth client secrets, third-party API keys) are **never auto-rotated** — those need the user's dashboard action. The script exits with a checklist and `handoff-gen.py` writes one markdown file per affected project at `~/security-incident-<YYYY-MM>-vercel/<project>.md` with exact vendor-dashboard steps.

### D. Vendor rotation — `scripts/update-env.py`
After you rotate a key in a vendor dashboard, paste the new value back:
```bash
python3 scripts/update-env.py <project> <KEY> --from-stdin
```
The script uploads with `type: sensitive`, triggers a redeploy if you pass `--redeploy`, and logs the change.

## Two `.gitignore` files — don't confuse them

This repo's own `.gitignore` covers **artifacts produced by running the toolkit on this machine** (rotation logs, audit snapshots, `.env`). It exists so a contributor cannot accidentally commit secrets while developing the toolkit.

You also need to harden the **repos that the toolkit operates on** — your Next.js / Remix / SvelteKit apps that live on Vercel. If you ever copy a handoff doc into one of those repos, or if `vercel env pull` writes a stale `.env`, you don't want them committed. Run:

```bash
python3 scripts/ignore-setup.py /path/to/your/app-repo
```

It appends the same patterns to `.gitignore`, `.vercelignore`, `.dockerignore`, `.npmignore` in the target repo. Idempotent — only adds what's missing.

> Default toolkit outputs land in `~/.vercel-security/` and `~/security-incident-*-vercel/` — both *outside* every repo. The ignore patterns are belt-and-suspenders for the case where you copy a handoff doc into a repo intentionally.

## Adversary model — what someone reading this repo learns

The toolkit is open-source by design. Assume an attacker has read every line. What they get:

- The **patterns** used to classify secrets (`HIGH_SECRET_PATTERNS` in `scripts/_common.py`) — these are obvious from any production codebase, not a secret advantage.
- The **path** to your local Vercel CLI auth file — already documented by Vercel.
- The **API endpoints** used — all public Vercel REST endpoints.

What they **do not** get from this repo:
- Your token (read at runtime from your local CLI, never embedded)
- The names, IDs, or env vars of any specific user's projects
- Any rotation log or audit snapshot
- Any plaintext value, ever

What the toolkit refuses to do, structurally, to limit harm if your machine is compromised:
- Accept secret values via CLI args (would land in shell history) — uses `getpass` only
- Print or log the Vercel CLI token, even on error
- Persist any plaintext rotation value to disk (yes, even `ADMIN_PASSWORD` — printed to stdout once, then dropped)
- Read or write outside `~/.vercel-security/`, `~/security-incident-*-vercel/`, and explicitly named target repo paths
- Make any network call to anything other than `api.vercel.com`

If you fork this repo and modify these guarantees, document the change loudly. Users should not need to read the diff to know the safety properties changed.

## Safety & privacy guarantees

- **No plaintext in this repo.** All sample outputs are redacted. Your values never leave your machine.
- **Dry-run by default** on any destructive action.
- **Local log only.** Rotation logs go to `~/.vercel-security/` with `0600` perms, not `/tmp`, not the repo.
- **Read token, don't copy it.** Scripts read the local Vercel CLI token from `~/Library/Application Support/com.vercel.cli/auth.json` (macOS) or `~/.local/share/com.vercel.cli/auth.json` (Linux) — they never print or transmit it.
- **Confirmations.** Every batch prompts `y/N` even with `--apply`.
- **Rollback log.** Every delete stores the old env id + target list so you can manually recreate if needed.
- **No workarounds.** Uses only documented Vercel REST API endpoints (`/v9/projects`, `/v10/projects/.../env`). No scraping, no undocumented flags.

## Runbooks

Process docs:
- [`00-incident-response.md`](runbooks/00-incident-response.md) — minute-by-minute playbook
- [`01-prevention-hardening.md`](runbooks/01-prevention-hardening.md) — defaults, 2FA, access reviews
- [`03-common-mistakes.md`](runbooks/03-common-mistakes.md) — gotchas, near-misses, what not to do

Per-vendor rotation:
- [Supabase](runbooks/vendor-supabase.md)
- [Google OAuth](runbooks/vendor-google-oauth.md)
- [Neon / Postgres](runbooks/vendor-neon.md)
- [Generic third-party API](runbooks/vendor-generic.md)

## Related

- [Vercel April 2026 security incident — official bulletin](https://vercel.com/kb/bulletin/vercel-april-2026-security-incident)
- [Remediating Vercel API access token leaks — GitGuardian](https://www.gitguardian.com/remediation/vercel-api-access-token)
- [Vercel sensitive environment variables docs](https://vercel.com/docs/environment-variables/sensitive-environment-variables)

## License

MIT.
