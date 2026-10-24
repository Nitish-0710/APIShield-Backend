from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import (
    AppException,
    CurrentUser,
    DbSession,
    enforce_rate_limit,
    verify_csrf,
)
from app.core.config import settings
from app.core.security import generate_csrf_token
from app.models.user import User
from app.schemas.auth import (
    UserRegisterRequest,
    UserLoginRequest,
    UserResponse,
    CsrfResponse,
)
from app.services.auth_service import (
    register_user,
    authenticate_user,
    create_session,
    invalidate_session,
    UserAlreadyExistsException,
    InvalidCredentialsException,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
    dependencies=[Depends(enforce_rate_limit)],
)
def register(
    data: UserRegisterRequest,
    db: DbSession,
):
    """
    Registers a new user account with hashed password storage.
    Enforces email uniqueness, minimal password length, and displays safe errors.
    """
    try:
        user = register_user(db, data)
        return user
    except UserAlreadyExistsException as exc:
        raise AppException(
            status_code=status.HTTP_409_CONFLICT,
            code="CONFLICT",
            message=str(exc),
            field_errors={"email": "An account with this email already exists."},
        )


@router.post(
    "/login",
    response_model=UserResponse,
    summary="Sign in and establish session",
    dependencies=[Depends(enforce_rate_limit)],
)
def login(
    data: UserLoginRequest,
    request: Request,
    response: Response,
    db: DbSession,
):
    """
    Authenticates user credentials and issues a secure HTTP-only session cookie.
    Prevents session fixation by provisioning a fresh session ID on every successful login.
    """
    try:
        user = authenticate_user(db, data)
    except InvalidCredentialsException as exc:
        raise AppException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="INVALID_CREDENTIALS",
            message=str(exc),
        )

    user_agent = request.headers.get("User-Agent")
    client_ip = request.client.host if request.client else None

    # Provision fresh session
    _, raw_token = create_session(
        db,
        user_id=user.id,
        user_agent=user_agent,
        ip_address=client_ip,
    )

    # Issue HTTP-only session cookie
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=raw_token,
        max_age=settings.SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite=settings.SESSION_COOKIE_SAMESITE,
        path="/",
    )

    # Issue CSRF cookie and header for subsequent state-changing calls
    csrf_token = generate_csrf_token()
    response.set_cookie(
        key=settings.CSRF_COOKIE_NAME,
        value=csrf_token,
        max_age=settings.SESSION_MAX_AGE_SECONDS,
        httponly=False,  # Client needs to read CSRF token or obtain via header
        secure=settings.SESSION_COOKIE_SECURE,
        samesite=settings.SESSION_COOKIE_SAMESITE,
        path="/",
    )
    response.headers["X-CSRF-Token"] = csrf_token

    return user


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current authenticated user profile",
)
def get_me(current_user: CurrentUser):
    """
    Returns the public profile of the authenticated user.
    Rejects unauthenticated requests with HTTP 401.
    """
    return current_user


@router.post(
    "/logout",
    summary="Invalidate session and sign out",
    dependencies=[Depends(verify_csrf)],
)
def logout(
    request: Request,
    response: Response,
    current_user: CurrentUser,
    db: DbSession,
):
    """
    Invalidates the active session in the database and clears authentication cookies.
    Requires valid CSRF verification for state-changing operation.
    """
    session_token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if session_token:
        invalidate_session(db, session_token)

    response.delete_cookie(key=settings.SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(key=settings.CSRF_COOKIE_NAME, path="/")

    return {"message": "Logged out successfully."}


@router.get(
    "/csrf",
    response_model=CsrfResponse,
    summary="Get fresh CSRF token",
)
def get_csrf(response: Response):
    """
    Supplies a fresh CSRF token and sets the CSRF cookie for client consumption.
    """
    token = generate_csrf_token()
    response.set_cookie(
        key=settings.CSRF_COOKIE_NAME,
        value=token,
        max_age=settings.SESSION_MAX_AGE_SECONDS,
        httponly=False,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite=settings.SESSION_COOKIE_SAMESITE,
        path="/",
    )
    response.headers["X-CSRF-Token"] = token
    return CsrfResponse(csrfToken=token)
