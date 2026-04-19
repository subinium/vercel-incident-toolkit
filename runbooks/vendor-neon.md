# Vendor runbook — Neon / Postgres connection string

Applies to Neon, Supabase Postgres direct connection, Render Postgres, and any other Postgres provider where the credential is embedded in `DATABASE_URL` / `POSTGRES_URL`.

## Pattern

`DATABASE_URL` looks like:
```
postgresql://<user>:<password>@<host>/<db>?sslmode=require
```

The credential is the `<password>` segment. Rotation = generate a new password, then update the connection string everywhere.

## Neon

1. **Neon console** → your project → Roles & Databases.
2. Find the role currently used for production (often `neondb_owner` or similar).
3. Click the role → **Reset password**.
4. Copy the new password. Construct the new connection string by swapping the password into the URL pattern.
5. Old password continues to work for a brief grace period on some plans — verify by running a query with the old credential after rotation.

## Supabase (direct connection, not REST)

1. Supabase dashboard → Settings → Database → **Reset database password**.
2. Copy the new connection string from the same page (it shows pooler vs direct vs session-mode separately).
3. **Verify pooler hostname format** — common gotcha. Format: `aws-0-<region>.pooler.supabase.com` for pooler, direct host is different. Don't mix them up.

## Render / generic providers

Standard pattern: dashboard → DB → reset password → copy new connection string.

## After rotating

Upload the new full connection string to Vercel:
```
python3 scripts/update-env.py <project> DATABASE_URL --target production --from-stdin --apply
```

Don't forget:
- `DIRECT_URL` if used (separate from pooled `DATABASE_URL` for migration tools like Prisma)
- `POSTGRES_PRISMA_URL`, `POSTGRES_URL_NON_POOLING` if used
- Local `.env` for every developer: `vercel env pull`
- CI secrets (GitHub Actions etc.)

## Side effects

- Active database connections drop on the rotation; serverless functions reconnect with the new credential on the next request.
- Long-running migration scripts started with the old credential complete normally; new ones use the new one.
- ORM connection pools may take a moment to discover the change. A `vercel --prod` redeploy ensures all functions cold-start with the new value.

## Verification

- Hit a production endpoint that issues a DB query
- Check Neon/Supabase Logs for connection attempts using the old password (there should be none after a few minutes)
- Re-run `python3 scripts/audit.py` to confirm the new env is `sensitive`

## Common mistakes

- **Trailing whitespace / newline in the new env value.** A `\n` at the end of the connection string makes Postgres reject every query with a cryptic error. The toolkit's `update-env.py --from-stdin` strips trailing whitespace, but verify.
- **Wrong pooler URL.** Pooled and direct connections use different hosts. Migrations need direct. Runtime queries usually want pooled.
- **Forgetting `?sslmode=require`.** Some providers reject non-SSL.
- **Embedding credentials in `vercel.json`.** Don't. Use env vars only.
