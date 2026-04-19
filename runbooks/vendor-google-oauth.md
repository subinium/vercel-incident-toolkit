# Vendor runbook — Google OAuth

Rotate the OAuth 2.0 client secret used for Google Sign-In, Workspace API access, etc.

Affected env vars typically: `AUTH_GOOGLE_SECRET`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_OAUTH_SECRET`.

## Steps

1. **Google Cloud Console** → APIs & Services → Credentials.
2. Find the OAuth 2.0 Client ID matching your project (the one whose `Authorized redirect URIs` points at your Vercel app).
3. Click the client name → **Reset Secret** at the top.
4. Confirm the warning. The old secret is invalidated immediately.
5. Copy the new client secret.

## Side effects

- All in-flight OAuth handshakes using the old secret fail. Users mid-login get redirected back to start.
- Any backend that exchanges authorization codes for tokens using the old secret fails until updated.
- Existing access tokens already issued continue to work until they expire (1 hour by default for Google).
- Refresh tokens continue to work unless you explicitly revoke the consent grant.

## Upload to Vercel

```
python3 scripts/update-env.py <project> AUTH_GOOGLE_SECRET --target production --from-stdin --apply
```

Repeat for `preview` and `development` if you use the same client ID across environments. **Better practice**: separate OAuth client per environment — production gets its own client, preview/dev use a separate test client. Don't share the production secret across non-prod environments.

## Verification

- Sign-in flow: log out → sign in → confirm you reach your authenticated landing page
- Check application logs for `invalid_client` errors — these mean a consumer wasn't updated

## If the secret was suspected leaked (not just rotation hygiene)

- Revoke any **refresh tokens** issued under that secret. Users → Account Settings → Connected apps → revoke. (You can also do this programmatically via Google's revoke endpoint.)
- Audit Google Cloud Console → Audit Logs for the OAuth client during the suspected leak window.

## Common mistakes

- Forgetting to update redirect URIs after deploying to a new domain. The error is generic ("redirect_uri_mismatch"). Compare exact protocol + host + path.
- Using one OAuth client across prod and preview. A leak in preview = prod compromise.
- Hard-coding `AUTH_GOOGLE_ID` (the client ID) and rotating only the secret. The ID is fine to keep — it's not a credential. Rotate the secret only.
