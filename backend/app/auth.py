"""
Phase 8: HTTP Basic auth across the API, with a public read-only surface.

The API serves two audiences that need different things. A recruiter opening
the link should see a working dashboard immediately -- a login wall on a
portfolio piece is the same as a broken link. The owner's own commit history
should stay private.

So there are two tiers, and the split is by DATA, not only by route:

  PUBLIC   GET on the read endpoints, restricted to profiles flagged
           is_sample -- public GitHub accounts seeded as demo data. No
           credentials, nothing of the owner's exposed.
  PRIVATE  Everything else: the owner's own profile, POST /api/refresh, and
           the auto-generated /docs. HTTP Basic, as before.

This middleware decides only whether credentials were *presented and valid*
and records that on request.state. Which profiles a given caller may see is
enforced in the route handlers, because that question needs the database and
a middleware has no business opening a session to answer it.

Why a middleware at all: it cannot be forgotten. A new endpoint added
tomorrow is private by default and has to opt in to PUBLIC_READ_PATHS to
become reachable, which is the correct direction for a mistake to fall.
"""

import base64
import binascii
import logging
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from .config import settings

log = logging.getLogger(__name__)

# Reachable without credentials no matter what: Render's health probe.
PUBLIC_PATHS = {"/health"}

# Reachable without credentials on GET when PUBLIC_DEMO is on. The handlers
# behind these paths must restrict an unauthenticated caller to sample
# profiles -- being listed here does not make their data public, it makes the
# route reachable so the handler can decide.
PUBLIC_READ_PATHS = {
    "/api/profiles",
    "/api/skills",
    "/api/skills/history",
    "/api/commits",
    "/api/status",
}

UNAUTHORIZED_HEADERS = {"WWW-Authenticate": 'Basic realm="Undrift"'}


def is_authenticated(request: Request) -> bool:
    """
    Whether this request carried valid credentials.

    Defaults to False when the attribute is missing, so any code path that
    somehow bypasses the middleware is treated as anonymous rather than
    trusted.
    """
    return bool(getattr(request.state, "authenticated", False))


def _credentials_match(header_value: str) -> bool:
    """
    Validate an `Authorization: Basic <base64>` header.

    Uses compare_digest rather than == so that comparison time doesn't depend
    on how many leading characters were correct -- the standard defence
    against timing attacks on secret comparison.
    """
    scheme, _, encoded = header_value.partition(" ")
    if scheme.lower() != "basic" or not encoded:
        return False

    try:
        decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return False

    username, _, password = decoded.partition(":")

    # Both comparisons always run -- no early return on a bad username --
    # so a wrong username and a wrong password take the same time.
    user_ok = secrets.compare_digest(username, settings.app_username)
    pass_ok = secrets.compare_digest(password, settings.app_password)
    return user_ok and pass_ok


class BasicAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        # Record whether valid credentials were presented, regardless of
        # whether this route needs them. Handlers use this to decide how much
        # of the data to show, so it has to be set on every path.
        header = request.headers.get("Authorization")
        credentials_ok = bool(header) and _credentials_match(header)
        request.state.authenticated = credentials_ok

        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        # CORS preflights never carry credentials. CORSMiddleware sits outside
        # this one and normally answers them first; this is a safety net.
        if request.method == "OPTIONS":
            return await call_next(request)

        if credentials_ok:
            return await call_next(request)

        # Anonymous from here down. The public demo surface is GET-only: a
        # write is never anonymous, whatever path it targets.
        if (
            settings.public_demo
            and request.method == "GET"
            and request.url.path in PUBLIC_READ_PATHS
        ):
            return await call_next(request)

        # Fail closed. A deployment with no credentials configured refuses
        # private requests rather than quietly serving them -- exactly the
        # failure nobody notices. The public surface above is unaffected,
        # because it is public by design rather than by misconfiguration.
        if not settings.app_username or not settings.app_password:
            log.error("APP_USERNAME / APP_PASSWORD are not set; refusing private requests.")
            return JSONResponse(
                {"detail": "Server auth is not configured."}, status_code=503
            )

        return JSONResponse(
            {"detail": "Not authenticated"},
            status_code=401,
            headers=UNAUTHORIZED_HEADERS,
        )
