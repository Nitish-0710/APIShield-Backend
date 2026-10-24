from typing import Annotated
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.middleware import validate_csrf_for_request, rate_limiter
from app.db.session import get_db
from app.models.user import User
from app.services.auth_service import get_user_by_session_token


class AppException(HTTPException):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        field_errors: dict[str, str] | None = None,
    ):
        super().__init__(status_code=status_code, detail=message)
        self.code = code
        self.message = message
        self.field_errors = field_errors or {}


def verify_csrf(request: Request) -> None:
    """Dependency that enforces CSRF on state-changing cookie-authenticated requests."""
    if not validate_csrf_for_request(request):
        raise AppException(
            status_code=status.HTTP_403_FORBIDDEN,
            code="CSRF_ERROR",
            message="Invalid or missing CSRF token.",
        )


def enforce_rate_limit(request: Request) -> None:
    """Dependency that enforces basic sliding-window rate limit per client IP."""
    client_ip = request.client.host if request.client else "unknown"
    if not rate_limiter.is_allowed(client_ip):
        raise AppException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            code="RATE_LIMITED",
            message="Too many requests. Please slow down and try again later.",
        )


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """Extract and validate the authenticated user from the HTTP-only session cookie."""
    session_token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not session_token:
        raise AppException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="UNAUTHORIZED",
            message="Authentication required. Please sign in.",
        )

    user = get_user_by_session_token(db, session_token)
    if not user:
        raise AppException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="UNAUTHORIZED",
            message="Session is invalid or has expired. Please sign in again.",
        )

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[Session, Depends(get_db)]
