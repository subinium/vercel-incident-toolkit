# Security policy — for this toolkit itself

This toolkit handles secrets. That makes the toolkit itself a target. Read this before installing.

## Supply chain

- **Pin to a commit, not `main`.** Forks of this repo can be malicious. Either install from the upstream URL or pin to a specific commit/tag you've reviewed.
- **No runtime dependencies.** Every script uses only the Python standard library. If you see a `requirements.txt` or `package.json` in your copy, that copy has been tampered with — discard it.
- **No network calls except to `api.vercel.com`.** Audit `grep -r 'urllib\|requests\|http' scripts/` before running. Anything pointing elsewhere is a red flag.
- **No telemetry.** This toolkit does not send anything anywhere except your own Vercel API endpoint.

## Token handling

- The Vercel API token is read from the local CLI auth file (`~/Library/Application Support/com.vercel.cli/auth.json` on macOS, `~/.local/share/com.vercel.cli/auth.json` on Linux). It is **never printed, logged, or transmitted**.
- After running any flow during an active incident, **rotate the token**: `vercel logout && vercel login`.
- If you have multiple machines logged in, `vercel logout` on one does not invalidate the others. Run on each, or revoke all tokens via Vercel Dashboard → Account Settings → Tokens.

## Output handling

- All logs and snapshots write to `~/.vercel-security/` (mode `0600`) or `~/security-incident-<YYYY-MM>-vercel/` (mode `0700`). They are **never** written into a repo directory.
- These paths must be in `.gitignore`, `.vercelignore`, `.dockerignore`, `.npmignore` — `scripts/ignore-setup.py` will add them for you.
- A newly generated `ADMIN_PASSWORD` is the only plaintext value the rotation log retains. Move it into a password manager and delete the log entry.

## Reporting a vulnerability

If you find a security issue with this toolkit, please open a private security advisory on GitHub instead of a public issue.

## What this toolkit will refuse to do

- Run any destructive operation without `--apply` and `y/N` confirmation
- Auto-rotate external vendor keys (Supabase, OAuth, DB providers, third-party APIs)
- Push to a git repo
- Modify shell rc files, system keychain, or other global configuration
- Use undocumented Vercel API endpoints
- Print or log the Vercel CLI token
