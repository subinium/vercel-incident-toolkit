# Vendor runbook — Google OAuth

Rotate the OAuth 2.0 client secret used for Google Sign-In, Workspace API access, etc.

Affected env vars typically: `AUTH_GOOGLE_SECRET`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_OAUTH_SECRET`.

## Steps

Google's current rotation flow is **two-secret overlap**, not replace-in-place — old and new secrets work concurrently until you manually disable the old one. There is no "Reset Secret" button today.

1. **Google Cloud Console** → APIs & Services → Credentials.
2. Find the OAuth 2.0 Client ID matching your project (the one whose `Authorized redirect URIs` points at your Vercel app).
3. Click the client name → **Add Secret** at the top. A new secret appears alongside the existing one, both enabled.
4. Copy the new client secret. It is only shown once.
5. Upload the new secret to Vercel and redeploy (see below). Verify in production that the new secret is the one actually being used (check application logs).
6. Back in Google Cloud Console, **Disable** the old secret. Wait, confirm nothing broke.
7. **Delete** the old secret once you're confident.

Refer to Google's official guide for the current UI and edge cases: [Manage OAuth Clients](https://support.google.com/cloud/answer/15549257).

## Side effects

- During the overlap window (step 3 → step 6), **both** secrets are valid. This is the safe-rotation window Google provides.
- After Disable (step 6): any backend still using the old secret fails on the next token exchange.
- Existing access tokens already issued continue to work until they expire (1 hour default).
- Refresh tokens continue to work unless you explicitly revoke the consent grant. They will be used with whichever client secret the exchanging backend now holds.

## Upload to Vercel

```
python3 scripts/update-env.py <project> AUTH_GOOGLE_SECRET --target production --from-stdin --apply
```

Repeat for `preview` and `development` if you use the same client ID across environments. **Better practice**: separate OAuth client per environment — production gets its own client, preview/dev use a separate test client. Don't share the production secret across non-prod environments.

## Verification

- Sign-in flow: log out → sign in → confirm you reach your authenticated landing page
- Check application logs for `invalid_client` errors — these mean a consumer wasn't updated

## If the secret was suspected leaked (not just rotation hygiene)

- **Skip the overlap window.** Immediately after step 3 (Add Secret), disable the old secret — do not leave both enabled.
- Revoke any **refresh tokens** issued under that secret. Users → Account Settings → Connected apps → revoke. (You can also do this programmatically via Google's revoke endpoint.)
- Audit Google Cloud Console → Audit Logs for the OAuth client during the suspected leak window.

## Common mistakes

- Forgetting to update redirect URIs after deploying to a new domain. The error is generic ("redirect_uri_mismatch"). Compare exact protocol + host + path.
- Using one OAuth client across prod and preview. A leak in preview = prod compromise.
- Hard-coding `AUTH_GOOGLE_ID` (the client ID) and rotating only the secret. The ID is fine to keep — it's not a credential. Rotate the secret only.
