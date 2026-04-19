# Vendor runbook — Supabase

Rotate Supabase service role key, JWT secret, and (if needed) anon key.

## Service role key — `SUPABASE_SERVICE_ROLE_KEY`

This key bypasses Row Level Security. If it leaks, treat as full DB compromise.

1. **Supabase dashboard** → your project → Settings → API.
2. Click the regenerate icon next to **service_role secret**.
3. Confirm. The old key stops working immediately.
4. Copy the new value (Supabase shows it once on this screen — you can re-display from this same screen as long as you're authenticated).

Side effects:
- Any backend service using the old key fails immediately. List them first.
- Common consumers: Vercel functions, GitHub Actions, scheduled jobs, ETL pipelines, admin scripts.

After rotating in Supabase, upload to Vercel for every project that uses it:
```
python3 scripts/update-env.py <project-name> SUPABASE_SERVICE_ROLE_KEY --target production --from-stdin --apply
python3 scripts/update-env.py <project-name> SUPABASE_SERVICE_ROLE_KEY --target preview --from-stdin --apply
python3 scripts/update-env.py <project-name> SUPABASE_SERVICE_ROLE_KEY --target development --from-stdin --apply
```

Then update non-Vercel consumers:
- GitHub Actions: Settings → Secrets and variables → Actions → update each
- Local dev: each developer runs `vercel env pull` in their project dir

Trigger production redeploy and smoke test:
```
vercel --prod --cwd /path/to/project
```

## JWT secret — `SUPABASE_JWT_SECRET`

Rotating invalidates **every existing JWT** issued by Supabase, including refresh tokens. Every signed-in user is logged out.

1. Settings → API → JWT Secret → Generate new secret.
2. Save the new value, upload to Vercel as above.
3. Communicate the forced-logout to users if customer-facing.

## Anon key — `SUPABASE_ANON_KEY` / `NEXT_PUBLIC_SUPABASE_ANON_KEY`

The anon key is **designed to be public** — it ships in the browser bundle. Row Level Security is what protects your data.

In normal operation: do not rotate. If your RLS policies are weak and the anon key is being abused, the fix is RLS, not rotation.

In a "rotate everything anyway" panic:
1. Settings → API → Generate new anon key (this is gated behind support on some plans).
2. Update everywhere: Vercel, all client builds, all mobile apps. Old key continues working until you delete it.

## Database password (if connecting via direct connection string, not REST)

- Settings → Database → Reset password.
- Update `DATABASE_URL` / `POSTGRES_URL` everywhere. See `vendor-neon.md` for the connection-string pattern (same applies to Supabase Postgres).

## Verification

- Load the production app, sign in, exercise a query that uses service role
- Check Supabase logs (Logs → Postgres → recent queries) — confirm queries land
- Re-run `python3 scripts/audit.py` to confirm new env type is `sensitive`
