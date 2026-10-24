import os
import pytest
from pydantic import ValidationError
from app.core.config import Settings, DEFAULT_DEV_SECRET, DEFAULT_DEV_ENCRYPTION_KEY



def test_production_rejects_default_dev_secret(monkeypatch):
    """Production configuration must reject the default development secret."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", DEFAULT_DEV_SECRET)

    with pytest.raises(ValidationError) as excinfo:
        Settings()

    assert "must not use the default development secret" in str(excinfo.value)


def test_production_rejects_short_secret(monkeypatch):
    """Production configuration must reject secrets shorter than 32 characters."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "too-short-secret")

    with pytest.raises(ValidationError) as excinfo:
        Settings()

    assert "at least 32 characters long" in str(excinfo.value)


def test_production_rejects_placeholder_secret(monkeypatch):
    """Production configuration must reject placeholder or change-me secrets."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "this-is-a-long-change-in-production-key-value")

    with pytest.raises(ValidationError) as excinfo:
        Settings()

    assert "placeholder pattern 'change-in-production'" in str(excinfo.value)


def test_production_rejects_low_entropy_secret(monkeypatch):
    """Production configuration must reject repetitive/low-entropy secrets."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")  # 32 identical chars

    with pytest.raises(ValidationError) as excinfo:
        Settings()

    assert "high-entropy" in str(excinfo.value)


def test_production_accepts_strong_explicit_secret(monkeypatch):
    """Production configuration must accept a strong, unique, non-default secret and encryption key."""
    strong_secret = "c987f2e105d10984a1e948f2a1b94e019f390d4e928a719c8f2b1d0e49f82a17"
    strong_enc_key = "1YQPxaczA0AzH2MIGJZI48m83ps-A-iyCEstmJ1tSk8="
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", strong_secret)
    monkeypatch.setenv("CREDENTIALS_ENCRYPTION_KEY", strong_enc_key)

    config = Settings()
    assert config.ENVIRONMENT == "production"
    assert config.SECRET_KEY == strong_secret
    assert config.CREDENTIALS_ENCRYPTION_KEY == strong_enc_key


def test_production_rejects_default_encryption_key(monkeypatch):
    """Production configuration must reject the default dev encryption key."""
    strong_secret = "c987f2e105d10984a1e948f2a1b94e019f390d4e928a719c8f2b1d0e49f82a17"
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", strong_secret)
    monkeypatch.setenv("CREDENTIALS_ENCRYPTION_KEY", DEFAULT_DEV_ENCRYPTION_KEY)

    with pytest.raises(ValidationError) as excinfo:
        Settings()


    assert "CREDENTIALS_ENCRYPTION_KEY must not use the default development key" in str(excinfo.value)


def test_encryption_key_cannot_reuse_secret_key(monkeypatch):
    """CREDENTIALS_ENCRYPTION_KEY must never be identical to SECRET_KEY."""
    fernet_key = "1YQPxaczA0AzH2MIGJZI48m83ps-A-iyCEstmJ1tSk8="
    monkeypatch.setenv("SECRET_KEY", fernet_key)
    monkeypatch.setenv("CREDENTIALS_ENCRYPTION_KEY", fernet_key)

    with pytest.raises(ValidationError) as excinfo:
        Settings()

    assert "CREDENTIALS_ENCRYPTION_KEY must not reuse SECRET_KEY" in str(excinfo.value)


def test_invalid_fernet_key_rejected(monkeypatch):
    """Malformed or invalid length Fernet keys are rejected."""
    monkeypatch.setenv("CREDENTIALS_ENCRYPTION_KEY", "not-a-valid-fernet-key")

    with pytest.raises(ValidationError) as excinfo:
        Settings()

    assert "valid 32-byte base64-encoded Fernet key" in str(excinfo.value)



def test_development_and_test_usable_with_default_settings(monkeypatch):
    """Development and testing modes remain usable with the safe default development secret."""
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("SECRET_KEY", DEFAULT_DEV_SECRET)

    dev_config = Settings()
    assert dev_config.ENVIRONMENT == "development"
    assert dev_config.SECRET_KEY == DEFAULT_DEV_SECRET

    monkeypatch.setenv("ENVIRONMENT", "testing")
    test_config = Settings()
    assert test_config.ENVIRONMENT == "testing"


def test_development_rejects_short_secret(monkeypatch):
    """Even in development, secrets shorter than 32 characters are rejected."""
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("SECRET_KEY", "short-dev-secret")

    with pytest.raises(ValidationError) as excinfo:
        Settings()

    assert "at least 32 characters long" in str(excinfo.value)
