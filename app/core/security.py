import hashlib
import hmac
import secrets
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError

# Argon2id password hasher with secure recommended parameters
_hasher = PasswordHasher(
    time_cost=2,
    memory_cost=19456,  # 19 MiB
    parallelism=1,
    hash_len=32,
    salt_len=16,
)


def hash_password(password: str) -> str:
    """Hash a plaintext password using Argon2id."""
    return _hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against an Argon2id hash."""
    try:
        return _hasher.verify(hashed_password, plain_password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def generate_session_token() -> str:
    """Generate a high-entropy cryptographically secure session token."""
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    """Hash session token using SHA-256 for secure database lookup."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_csrf_token() -> str:
    """Generate a cryptographically secure CSRF token."""
    return secrets.token_urlsafe(32)


def verify_csrf_token(token_from_header: str, token_from_cookie: str) -> bool:
    """Verify CSRF token using constant-time comparison."""
    if not token_from_header or not token_from_cookie:
        return False
    return hmac.compare_digest(token_from_header, token_from_cookie)


def encrypt_credential(secret: str) -> str:
    """Encrypt a secret credential string at rest using Fernet authenticated encryption."""
    if not secret:
        return ""
    from app.core.config import settings
    from cryptography.fernet import Fernet
    f = Fernet(settings.CREDENTIALS_ENCRYPTION_KEY.encode("utf-8"))
    return f.encrypt(secret.encode("utf-8")).decode("utf-8")


def decrypt_credential(encrypted_token: str) -> str:
    """Decrypt an encrypted credential token. Raises ValueError if invalid or decryption fails."""
    if not encrypted_token:
        return ""
    from app.core.config import settings
    from cryptography.fernet import Fernet, InvalidToken
    f = Fernet(settings.CREDENTIALS_ENCRYPTION_KEY.encode("utf-8"))
    try:
        return f.decrypt(encrypted_token.encode("utf-8")).decode("utf-8")
    except (InvalidToken, Exception):
        raise ValueError("Decryption failed: invalid or corrupt credential token")

