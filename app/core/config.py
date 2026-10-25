from typing import List, Literal, Union
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_DEV_SECRET: str = "apishield-dev-secret-key-change-in-production-min32chars"
DEFAULT_DEV_ENCRYPTION_KEY: str = "vME3wCp5mpWfOD-IFGp1koWNHgtnGUKnY00-_-WDAEE="
DISALLOWED_PRODUCTION_SUBSTRINGS: tuple[str, ...] = (
    "change-in-production",
    "placeholder",
    "changeme",
    "replace-me",
    "example",
    "dev-secret",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    PROJECT_NAME: str = "APIShield Backend"
    VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"
    ENVIRONMENT: Literal["development", "testing", "production"] = "development"
    DEBUG: bool = False
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    # Security
    SECRET_KEY: str = Field(
        default=DEFAULT_DEV_SECRET,
        description="Key used for cryptographic signing and session derivation",
    )
    CREDENTIALS_ENCRYPTION_KEY: str = Field(
        default=DEFAULT_DEV_ENCRYPTION_KEY,
        description="Fernet key (32 urlsafe base64 bytes) for encrypting stored credentials at rest",
    )
    SESSION_COOKIE_NAME: str = "apishield_session"
    CSRF_COOKIE_NAME: str = "apishield_csrf"
    SESSION_MAX_AGE_SECONDS: int = 86400  # 24 hours
    SESSION_COOKIE_SECURE: bool = False
    SESSION_COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"

    # Database
    DATABASE_URL: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/apishield",
        description="SQLAlchemy database URL",
    )
    DATABASE_ECHO: bool = False

    # CORS
    CORS_ORIGINS: Union[List[str], str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]

    # Rate limiting (per minute per IP for sensitive auth operations)
    AUTH_RATE_LIMIT_PER_MINUTE: int = 20

    # Automated Monitoring
    MONITORING_ENABLED: bool = True
    MONITORING_TICK_SECONDS: int = 5
    MONITORING_MAX_CONCURRENCY: int = 10


    @field_validator("CORS_ORIGINS", mode="after")
    @classmethod
    def assemble_cors_origins(cls, v: Union[List[str], str]) -> List[str]:
        if isinstance(v, str):
            if v.startswith("[") and v.endswith("]"):
                import json
                try:
                    return json.loads(v)
                except Exception:
                    pass
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, (list, tuple)):
            return list(v)
        return []

    @model_validator(mode="after")
    def validate_security_configuration(self) -> "Settings":
        key = self.SECRET_KEY.strip() if self.SECRET_KEY else ""

        if len(key) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters long.")

        enc_key = self.CREDENTIALS_ENCRYPTION_KEY.strip() if self.CREDENTIALS_ENCRYPTION_KEY else ""
        if not enc_key:
            raise ValueError("CREDENTIALS_ENCRYPTION_KEY must not be empty.")

        if enc_key == key:
            raise ValueError("CREDENTIALS_ENCRYPTION_KEY must not reuse SECRET_KEY.")

        from cryptography.fernet import Fernet
        try:
            Fernet(enc_key.encode("utf-8"))
        except Exception as e:
            raise ValueError(f"CREDENTIALS_ENCRYPTION_KEY must be a valid 32-byte base64-encoded Fernet key: {e}")

        if self.ENVIRONMENT == "production":
            if key == DEFAULT_DEV_SECRET:
                raise ValueError(
                    "In production, SECRET_KEY must not use the default development secret. "
                    "Configure a strong, random production SECRET_KEY via environment variables."
                )

            key_lower = key.lower()
            for pattern in DISALLOWED_PRODUCTION_SUBSTRINGS:
                if pattern in key_lower:
                    raise ValueError(
                        f"In production, SECRET_KEY must not contain placeholder pattern '{pattern}'."
                    )

            if len(set(key)) < 8:
                raise ValueError("In production, SECRET_KEY must be high-entropy and non-repetitive.")

            if enc_key == DEFAULT_DEV_ENCRYPTION_KEY:
                raise ValueError(
                    "In production, CREDENTIALS_ENCRYPTION_KEY must not use the default development key. "
                    "Configure a strong, unique Fernet key via environment variables."
                )

            enc_key_lower = enc_key.lower()
            for pattern in DISALLOWED_PRODUCTION_SUBSTRINGS:
                if pattern in enc_key_lower:
                    raise ValueError(
                        f"In production, CREDENTIALS_ENCRYPTION_KEY must not contain placeholder pattern '{pattern}'."
                    )

        return self


settings = Settings()
