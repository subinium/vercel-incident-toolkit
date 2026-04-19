# Vendor runbook — generic third-party API

Use when the affected key doesn't have a dedicated runbook (Stripe, OpenAI, Anthropic, Resend, AWS, Sentry, etc.).

## Universal pattern

1. **Identify the dashboard.** The env var name usually maps to a vendor: `STRIPE_*` → Stripe, `OPENAI_API_KEY` → OpenAI, `RESEND_API_KEY` → Resend.
2. **Sign in to the vendor dashboard with 2FA.** If you don't have 2FA enabled there, set it up before rotating.
3. **Find the API keys / credentials section.** Common paths:
   - "API Keys", "Credentials", "Access Tokens", "App Settings → Secrets"
4. **Create a new key with the same scope as the old one.** Most vendors support multiple active keys — create new before deleting old to avoid downtime.
5. **Update Vercel:**
   ```
   python3 scripts/update-env.py <project> <KEY_NAME> --target production --from-stdin --apply
   ```
6. **Trigger redeploy.** `vercel --prod --cwd /path/to/project` or push a commit.
7. **Smoke test** the feature that uses this key.
8. **Revoke the old key** in the vendor dashboard. Only do this once smoke tests pass.

## Per-vendor notes

### Stripe
- Use **restricted keys** (Stripe Dashboard → Developers → API keys → "Create restricted key") rather than the secret key when possible.
- Webhook signing secrets (`STRIPE_WEBHOOK_SECRET`) are separate — rotate them if the webhook endpoint URL changed or you suspect leak.
- Stripe shows the new key only once on creation. Capture immediately.

### OpenAI / Anthropic
- Both let you create multiple keys. Create new → deploy → revoke old.
- Anthropic: Console → Settings → API Keys.
- OpenAI: Platform → API Keys.
- Both bill per key — confirm new key has correct organization assignment.

### Resend / SendGrid / Postmark (transactional email)
- A leaked email key can send phishing on your domain. Rotate ASAP.
- Check SPF/DKIM are still valid after rotation if you're switching API key scopes.

### AWS (`AWS_SECRET_ACCESS_KEY`)
- Don't rotate access keys for IAM Users in production — switch to **IAM Roles** (instance profile) or **OIDC federation from Vercel** instead. Long-lived AWS keys in env vars are an anti-pattern.
- If you must use a key: IAM Console → Users → your user → Security credentials → Create access key, deploy, then mark old key inactive (don't delete immediately — keep for 24h to confirm rollback path).

### Sentry / Datadog / Logtail (observability)
- Lower urgency than data-access keys, but a leaked observability key can be abused for log injection or quota exhaustion.
- Rotate once per quarter regardless.

## When in doubt

If the vendor has a "rotate" button: use it.
If not: "create new + delete old" is always safer than "edit in place".
If the vendor has neither: contact their support. A vendor with no key rotation flow is a vendor you should reduce dependency on.
