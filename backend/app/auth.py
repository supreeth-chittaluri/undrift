"""
Phase 8: HTTP Basic auth across the whole API.

This is one half of keeping the deployment private. The other half is Vercel's
Deployment Protection on the frontend. See the README for why both exist.

Why a middleware rather than a per-route dependency: a middleware cannot be
forgotten. Add a new endpoint tomorrow and it is protected automatically,
whereas a dependency you forget to attach is a silently public route.

Only /health is public, so Render's health check can reach it without
credentials. Everything else -- including the auto-generated /docs -- requires
the username and password from the environment.
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

# Paths reachable without credentials.
PUBLIC_PATHS = {"/health"}

UNAUTHORIZED_HEADERS = {"WWW-Authenticate": 'Basic realm="Undrift"'}


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
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        # CORS preflights never carry credentials. CORSMiddleware sits outside
        # this one and normally answers them first; this is a safety net.
        if request.method == "OPTIONS":
            return await call_next(request)

        # Fail closed. If the deployment has no credentials configured, the
        # API refuses to serve rather than quietly becoming public -- which is
        # exactly the failure you would not notice.
        if not settings.app_username or not settings.app_password:
            log.error("APP_USERNAME / APP_PASSWORD are not set; refusing all requests.")
            return JSONResponse(
                {"detail": "Server auth is not configured."}, status_code=503
            )

        header = request.headers.get("Authorization")
        if not header or not _credentials_match(header):
            return JSONResponse(
                {"detail": "Not authenticated"},
                status_code=401,
                headers=UNAUTHORIZED_HEADERS,
            )

        return await call_next(request)
