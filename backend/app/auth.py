"""API-key authentication for external (server-to-server) access to /api.

Model
-----
- Programmatic consumers (e.g. the autonomous runner) authenticate with a key
  sent as ``X-API-Key: <key>`` or ``Authorization: Bearer <key>``, matched
  against the allowlist in ``DASHBOARD_API_KEYS``.
- The existing browser dashboard calls /api directly with no key; it is let
  through when its request carries one of the trusted browser ``Origin`` values
  (the same set used for CORS), so the UI keeps working.
- If no keys are configured (``DASHBOARD_API_KEYS`` empty), auth is disabled and
  /api is open — preserving local/dev behaviour unchanged.

Caveat: an ``Origin`` header is browser-set and can be spoofed by a non-browser
client, so the origin allowance is not a hard guarantee. It preserves today's
posture (CORS-only) while adding a real key path for programmatic consumers.
Hardening path: route the UI through a server-side proxy (BFF) that holds the
key, then remove the origin allowance so every /api call needs a key.
"""
import logging

from fastapi import HTTPException, Request, status

from .config import settings

logger = logging.getLogger(__name__)


def _provided_key(request: Request) -> str | None:
    k = request.headers.get("x-api-key")
    if k and k.strip():
        return k.strip()
    auth = request.headers.get("authorization", "")
    if auth[:7].lower() == "bearer ":
        token = auth[7:].strip()
        return token or None
    return None


async def require_api_key(request: Request) -> None:
    """FastAPI dependency: allow the request or raise 401.

    Preflight OPTIONS requests are never gated (CORS needs them to pass).
    """
    if request.method == "OPTIONS":
        return

    keys = settings.api_key_set()
    if not keys:
        return  # auth disabled (no keys configured)

    provided = _provided_key(request)
    if provided and provided in keys:
        return

    origin = request.headers.get("origin", "")
    if origin and origin in set(settings.allowed_origin_list()):
        return  # trusted browser dashboard (see module docstring caveat)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing or invalid API key",
        headers={"WWW-Authenticate": "ApiKey"},
    )
