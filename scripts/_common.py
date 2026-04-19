"""Shared helpers for the toolkit. Standard-library only."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

VERCEL_API = "https://api.vercel.com"

# These are the only keys we will ever auto-generate values for.
INTERNAL_RANDOM_KEYS: frozenset[str] = frozenset(
    {
        # Auth.js / NextAuth — session JWT signing
        "NEXTAUTH_SECRET",
        "AUTH_SECRET",
        # Remix / Express / Hono / Fastify — cookie & session signing
        "SESSION_SECRET",
        "COOKIE_SECRET",
        # PayloadCMS
        "PAYLOAD_SECRET",
        # Next.js — preview mode & on-demand ISR
        "PREVIEW_SECRET",
        "REVALIDATION_SECRET",
        # Vercel Cron authorization
        "CRON_SECRET",
        # Internal HMAC signing (rotating breaks old signatures — acceptable)
        "API_KEY_HMAC_SECRET",
        "HMAC_SECRET",
        # Simple admin login secret (rotate hash cascades to operator)
        "ADMIN_PASSWORD",
    }
)

# Never auto-rotate these — rotation breaks stateful data (at-rest encryption,
# refresh tokens, persistent signatures).
NEVER_ROTATE_PATTERNS: tuple[str, ...] = (
    "ENCRYPTION_KEY",
    "DATA_ENCRYPTION",
    "AT_REST",
    "MASTER_KEY",
    "FIELD_KEY",
    "KMS_KEY",
    # Refresh / JWT keys may sign long-lived tokens; defer to operator
    "JWT_SECRET",
    "JWT_PRIVATE",
    "REFRESH_TOKEN_SECRET",
    # External vendor secrets — handled via update-env.py after vendor rotation
    "SUPABASE",
    "STRIPE",
    "OPENAI",
    "ANTHROPIC",
    "RESEND",
    "SENDGRID",
    "DATABASE_URL",
    "DB_URL",
    "POSTGRES_URL",
    "GOOGLE_CLIENT",
    "GITHUB_CLIENT",
    "AWS_SECRET",
)

# Patterns that strongly indicate an external vendor secret (do not auto-rotate).
HIGH_SECRET_PATTERNS: tuple[str, ...] = (
    "SERVICE_ROLE",
    "PRIVATE_KEY",
    "PRIVATEKEY",
    "DATABASE_URL",
    "DB_URL",
    "POSTGRES_URL",
    "MONGODB_URI",
    "REDIS_URL",
    "API_KEY",
    "APIKEY",
    "_TOKEN",
    "_SECRET",
    "WEBHOOK_SIGNING",
    "STRIPE",
    "ANTHROPIC",
    "OPENAI",
    "OPENROUTER",
    "SUPABASE_SERVICE",
    "SUPABASE_JWT",
    "JWT",
    "CLERK_SECRET",
    "RESEND",
    "SENDGRID",
    "POSTMARK",
    "AWS_SECRET",
    "GITHUB_TOKEN",
    "GH_TOKEN",
    "VERCEL_TOKEN",
    "BLOB_READ_WRITE",
)


def auth_token_path() -> Path:
    """Locate the Vercel CLI auth file. Cross-platform but conservative."""
    candidates = [
        Path.home() / "Library/Application Support/com.vercel.cli/auth.json",
        Path.home() / ".local/share/com.vercel.cli/auth.json",
        Path.home() / "AppData/Roaming/com.vercel.cli/auth.json",
    ]
    for c in candidates:
        if c.exists():
            return c
    raise SystemExit("Vercel CLI auth file not found. Run `vercel login` first.")


def load_token() -> str:
    """Read the Vercel CLI token. NEVER print, return, or log this value."""
    if os.environ.get("VERCEL_TOKEN"):
        # Defensive: an env-injected token may not match the CLI session
        # and indicates an unusual setup. Refuse rather than guess.
        raise SystemExit(
            "VERCEL_TOKEN is set in your environment. Unset it before running this toolkit "
            "so we use the CLI session unambiguously."
        )
    data = json.loads(auth_token_path().read_text())
    if "token" not in data:
        raise SystemExit("auth.json has no 'token' field. Re-run `vercel login`.")
    return data["token"]


def headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {load_token()}",
        "Content-Type": "application/json",
    }


def api(
    method: str, path: str, team_id: str | None = None, body: dict | None = None
) -> dict:
    """Call Vercel REST API. Documented endpoints only."""
    url = VERCEL_API + path
    if team_id:
        sep = "&" if "?" in path else "?"
        url += f"{sep}teamId={team_id}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, headers=headers(), method=method, data=data)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        return {"__error__": f"HTTP {e.code}", "__body__": e.read().decode()[:300]}


def list_teams() -> list[dict]:
    return api("GET", "/v2/teams?limit=50").get("teams", [])


def list_projects(team_id: str | None) -> list[dict]:
    projects, until = [], None
    while True:
        path = "/v9/projects?limit=100"
        if until:
            path += f"&until={until}"
        page = api("GET", path, team_id)
        if "__error__" in page:
            raise RuntimeError(f"Project list failed: {page}")
        projects.extend(page.get("projects", []))
        nxt = page.get("pagination", {}).get("next")
        if not nxt:
            return projects
        until = nxt


def list_env(project_id: str, team_id: str | None) -> list[dict]:
    out = api("GET", f"/v9/projects/{project_id}/env", team_id)
    if "__error__" in out:
        raise RuntimeError(f"Env list failed for {project_id}: {out}")
    return out.get("envs", [])


def severity(key: str, env_type: str) -> str:
    k = key.upper()
    is_high = any(p in k for p in HIGH_SECRET_PATTERNS)
    if env_type == "sensitive":
        return "OK"
    if env_type == "encrypted" and is_high:
        return "HIGH"
    if env_type == "encrypted":
        return "MED"
    if env_type == "plain":
        return "LOW-PLAIN"
    return env_type


def is_public_key(key: str) -> bool:
    return key.upper().startswith(("NEXT_PUBLIC_", "PUBLIC_", "VITE_PUBLIC_"))


def workspace_dir() -> Path:
    """Local secret-bearing scratch dir. Mode 0700."""
    p = Path.home() / ".vercel-security"
    p.mkdir(mode=0o700, exist_ok=True)
    try:
        p.chmod(0o700)
    except PermissionError:
        pass
    return p


def confirm(prompt: str, default_no: bool = True) -> bool:
    """Interactive y/N prompt. Default no."""
    suffix = "[y/N]" if default_no else "[Y/n]"
    answer = input(f"{prompt} {suffix} ").strip().lower()
    if not answer:
        return not default_no
    return answer in ("y", "yes")


def write_secure(path: Path, data: str) -> None:
    """Write a file with 0600 perms (umask-safe)."""
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(data)


def red(msg: str) -> str:
    return f"\033[31m{msg}\033[0m" if sys.stdout.isatty() else msg


def yellow(msg: str) -> str:
    return f"\033[33m{msg}\033[0m" if sys.stdout.isatty() else msg


def green(msg: str) -> str:
    return f"\033[32m{msg}\033[0m" if sys.stdout.isatty() else msg
