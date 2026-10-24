from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import select, delete

from app.core.config import settings
from app.core.security import (
    hash_password,
    verify_password,
    generate_session_token,
    hash_session_token,
)
from app.models.user import User
from app.models.session import UserSession
from app.schemas.auth import UserRegisterRequest, UserLoginRequest


class UserAlreadyExistsException(Exception):
    pass


class InvalidCredentialsException(Exception):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def register_user(db: Session, data: UserRegisterRequest) -> User:
    """Register a new user account with hashed password."""
    existing = db.execute(
        select(User).where(User.email == data.email)
    ).scalar_one_or_none()
    if existing:
        raise UserAlreadyExistsException("An account with this email already exists.")

    user = User(
        name=data.name,
        email=data.email,
        password_hash=hash_password(data.password),
        role="developer",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, data: UserLoginRequest) -> User:
    """Authenticate user credentials safely without revealing account existence."""
    user = db.execute(
        select(User).where(User.email == data.email)
    ).scalar_one_or_none()

    if not user or not user.is_active:
        # Avoid timing attacks: still run verification against a dummy hash
        verify_password(data.password, "$argon2id$v=19$m=19456,t=2,p=1$dummy$dummy")
        raise InvalidCredentialsException("Invalid email or password.")

    if not verify_password(data.password, user.password_hash):
        raise InvalidCredentialsException("Invalid email or password.")

    return user


def create_session(
    db: Session,
    user_id: str,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> tuple[UserSession, str]:
    """
    Create a new persistent session.
    Returns (UserSession, raw_token). Only the SHA-256 hash is stored in the database.
    """
    raw_token = generate_session_token()
    token_hash = hash_session_token(raw_token)
    expires_at = utcnow() + timedelta(seconds=settings.SESSION_MAX_AGE_SECONDS)

    session = UserSession(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=expires_at,
        user_agent=user_agent[:255] if user_agent else None,
        ip_address=ip_address[:45] if ip_address else None,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session, raw_token


def get_user_by_session_token(db: Session, raw_token: str) -> User | None:
    """Validate a session token and return the associated active user."""
    if not raw_token:
        return None

    token_hash = hash_session_token(raw_token)
    now = utcnow()

    session = db.execute(
        select(UserSession)
        .where(UserSession.token_hash == token_hash, UserSession.expires_at > now)
    ).scalar_one_or_none()

    if not session or not session.user or not session.user.is_active:
        return None

    return session.user


def invalidate_session(db: Session, raw_token: str) -> bool:
    """Invalidate (delete) a session by its raw token."""
    if not raw_token:
        return False

    token_hash = hash_session_token(raw_token)
    result = db.execute(
        delete(UserSession).where(UserSession.token_hash == token_hash)
    )
    db.commit()
    return result.rowcount > 0
