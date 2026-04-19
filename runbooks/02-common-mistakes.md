# Runbook 03 — Common mistakes during incident response

Real failure modes seen during rotations. Read this before Flow C.

## Tooling

- **Running `rotate-internal.py --apply` on the wrong account.** The CLI session determines scope. Run `vercel whoami` first.
- **Running with `VERCEL_TOKEN` set in env.** It silently overrides the CLI session. The toolkit refuses to start in this state — don't try to "force" it.
- **Forgetting to run `audit.py` first.** Rotation reads from the latest snapshot. Stale snapshots = rotating env IDs that no longer exist.

## Coordination

- **Batching all external vendor rotations at once.** When something breaks, you can't tell which rotation caused it. Rotate, deploy, smoke test, then move on.
- **Forgetting CI mirrors.** `DATABASE_URL` is in Vercel and in your GitHub Actions secrets. Rotate Vercel only → CI starts failing on next push.
- **Not updating local `.env`.** After rotation, every developer's local `.env` is stale. `vercel env pull` in each project.
- **Webhook signature mismatch.** Rotating `API_KEY_HMAC_SECRET` breaks every consumer using the old HMAC. List consumers first; have new value ready to push to all of them.

## Sessions and downtime

- **Rotating `NEXTAUTH_SECRET` during peak traffic.** Every active session is invalidated. Schedule for off-peak.
- **Forgetting Vercel Cron.** `CRON_SECRET` rotation = next scheduled invocation 401s. If the cron is critical, update Vercel and any external schedulers atomically.
- **Stale preview deployments.** Old previews retain old env values and often have weaker auth. Run `vercel remove --safe` after rotation.

## Storage / leak vectors

- **Saving `ADMIN_PASSWORD` to a Notes app synced to iCloud.** Any cloud-synced note app is a copy off your machine. Use a password manager that encrypts client-side.
- **Pasting handoff docs into Slack/Discord.** Visible in message history forever. Share the path, not the contents. If sharing is necessary, share the handoff doc minus any plaintext value.
- **Backup-syncing `~/security-incident-*-vercel/`.** iCloud Drive, Dropbox, OneDrive — exclude these directories explicitly.
- **Screen-sharing during rotation.** Sensitive values can appear briefly in stdout. Stop sharing before running `--apply`.

## Project assumptions

- **Assuming "encrypted ≈ safe".** In a Vercel-side breach, encrypted is read with the server's key. Treat as plaintext-leaked.
- **Assuming "sensitive = invulnerable".** If the build infrastructure was reached, sensitive values used at build-time are also exposed. Prefer runtime-only access.
- **Forgetting `NEXT_PUBLIC_*`.** These ship to the client bundle. Anything sensitive prefixed with `NEXT_PUBLIC_` was already public — rotate at the source.

## Recovery

- **Running `--apply` twice by accident.** The second run finds the new env IDs (it re-reads audit), so it tries to rotate the freshly-rotated values. Effect: another rotation, another set of side effects. To avoid: re-run `audit.py` between attempts.
- **Lost the new `ADMIN_PASSWORD`.** Run `rotate-internal.py --apply` again. There is no recovery from the previous run.
- **Need to roll back.** The rotation log in `~/.vercel-security/rotations.json` records `old_env_id` and target list. Vercel cannot un-delete, so "rollback" means manually re-creating with a known-good value. If you don't have the old value, treat as an irreversible rotation.
