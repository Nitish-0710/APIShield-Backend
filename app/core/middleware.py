import time
import uuid
from collections import defaultdict
from typing import Callable, Dict, List
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings
from app.core.logging import logger
from app.core.security import verify_csrf_token, generate_csrf_token


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Assigns or propagates an X-Request-ID header on every request/response."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class RateLimiter:
    """Thread-safe in-memory sliding-window rate limiter for sensitive endpoints."""

    def __init__(self, limit_per_minute: int = 20):
        self.limit = limit_per_minute
        self.history: Dict[str, List[float]] = defaultdict(list)

    def is_allowed(self, client_ip: str) -> bool:
        now = time.time()
        window_start = now - 60.0

        # Purge timestamps outside the 60-second window
        timestamps = [t for t in self.history[client_ip] if t > window_start]
        self.history[client_ip] = timestamps

        if len(timestamps) >= self.limit:
            return False

        self.history[client_ip].append(now)
        return True


rate_limiter = RateLimiter(limit_per_minute=settings.AUTH_RATE_LIMIT_PER_MINUTE)


def validate_csrf_for_request(request: Request) -> bool:
    """
    Validates CSRF for state-changing cookie-authenticated requests.
    Expects CSRF token in 'X-CSRF-Token' header and matching 'apishield_csrf' cookie.
    """
    # Safe methods do not require CSRF checks
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return True

    # If no session cookie is present, this request is not cookie-authenticated
    session_cookie = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not session_cookie:
        return True

    csrf_header = request.headers.get("X-CSRF-Token") or request.headers.get("X-XSRF-Token")
    csrf_cookie = request.cookies.get(settings.CSRF_COOKIE_NAME)

    if not csrf_header or not csrf_cookie:
        return False

    return verify_csrf_token(csrf_header, csrf_cookie)
