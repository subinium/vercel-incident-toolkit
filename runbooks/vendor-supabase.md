# Vendor runbook — Supabase

Rotate Supabase service role key, JWT secret, and (if needed) anon key.

> **Two key systems coexist in 2026.** Supabase is transitioning from legacy JWT-based `anon` / `service_role` keys to a new API keys system (`sb_publishable_...` / `sb_secret_...`). Rotation mechanics differ between the two — check which your project uses before following any step below. Authoritative source: [Supabase — Rotating Anon, Service, and JWT Secrets](https://supabase.com/docs/guides/troubleshooting/rotating-anon-service-and-jwt-secrets-1Jq6yd) and [Understanding API keys](https://supabase.com/docs/guides/api/api-keys).

## Service role key — `SUPABASE_SERVICE_ROLE_KEY`

This key bypasses Row Level Security. If it leaks, treat as full DB compromise.

The legacy `service_role` key is a JWT signed by your project's JWT secret — it cannot be rotated on its own. You have two options:

- **Legacy key, urgent rotation:** rotate the JWT secret (see next section). This invalidates the `service_role` **and** the `anon` key **and** every outstanding user JWT. Expect full forced-logout and update every consumer.
- **Preferred path:** migrate to the new API keys system (`sb_secret_...`), where a compromised secret key can be rotated independently without touching the JWT secret or signing out users. New projects already default to this; existing projects can migrate via Dashboard → Project Settings → API Keys.

Follow the official rotation guide linked above for the exact UI — the dashboard is actively changing as Supabase phases legacy keys out.

Side effects (legacy path, via JWT secret rotation):
- Every outstanding user session JWT is invalidated — every signed-in user is logged out.
- The `anon` key changes at the same time; every client app (web, mobile) needs the new value.
- Any backend service using the old `service_role` fails. List them first: Vercel functions, GitHub Actions, scheduled jobs, ETL pipelines, admin scripts.

Side effects (new API keys path):
- Old and new `sb_secret_...` both work during the swap. Delete the old one only after every consumer is updated.

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

## JWT secret / JWT signing keys

Rotating the JWT secret invalidates **every outstanding JWT** issued by Supabase — all user sessions and the legacy `anon` / `service_role` keys (which are themselves JWTs). Every signed-in user is logged out.

UI is moving: older projects show **Settings → API → JWT Secret**; newer projects use **Project Settings → JWT Signing Keys** with asymmetric keys that support key IDs and overlap rotation. Follow Supabase's [JWT Signing Keys docs](https://supabase.com/docs/guides/auth/signing-keys) for the flow that matches your project.

After rotating:
1. Capture the new JWT secret / key.
2. Upload any app-side env var that holds it (commonly `SUPABASE_JWT_SECRET` for self-hosted or custom JWT verification).
3. Upload the new `anon` and `service_role` values to every Vercel project.
4. Communicate the forced-logout to users if customer-facing.

## Anon key — `SUPABASE_ANON_KEY` / `NEXT_PUBLIC_SUPABASE_ANON_KEY`

The anon key is **designed to be public** — it ships in the browser bundle. Row Level Security is what protects your data.

In normal operation: do not rotate. If your RLS policies are weak and the anon key is being abused, the fix is RLS, not rotation.

For legacy projects, the `anon` key is a JWT — it cannot be rotated independently. Rotating it means rotating the JWT secret, which also rotates `service_role` and logs out all users (see section above). For new-API-keys projects, the `sb_publishable_...` counterpart can be rotated independently via the API Keys dashboard; old and new both work during overlap.

## Database password (if connecting via direct connection string, not REST)

- Settings → Database → Reset password.
- Update `DATABASE_URL` / `POSTGRES_URL` everywhere. See `vendor-neon.md` for the connection-string pattern (same applies to Supabase Postgres).

## Verification

- Load the production app, sign in, exercise a query that uses service role
- Check Supabase logs (Logs → Postgres → recent queries) — confirm queries land
- Re-run `python3 scripts/audit.py` to confirm new env type is `sensitive`
