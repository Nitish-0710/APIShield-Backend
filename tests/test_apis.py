import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.api import ApiEndpoint
from app.models.user import User
from app.core.security import decrypt_credential


def sample_api_payload():
    return {
        "name": "Production Payment Gateway",
        "url": "https://api.stripe.com/v1/charges",
        "method": "POST",
        "queryParams": [{"key": "limit", "value": "10"}],
        "headers": [{"key": "Accept", "value": "application/json"}],
        "authType": "bearer",
        "secret": "sk_test_super_secret_key_12345",
        "body": '{"amount": 2000}',
        "expectedStatus": 200,
        "validationRule": "status == 200",
        "timeoutMs": 5000,
        "intervalSec": 60,
        "maxLatencyMs": 500,
        "errorRateThreshold": 2.0,
        "expectedAvailability": 99.9,
        "riskThreshold": 65.0,
        "monitoring": True,
    }


def test_create_api_success(
    authenticated_client: TestClient,
    auth_headers: dict,
    db_session: Session,
):
    """Authenticated user creates an API endpoint; secret is encrypted and hasSecret is True."""
    payload = sample_api_payload()
    resp = authenticated_client.post(
        "/api/v1/apis",
        json=payload,
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == payload["name"]
    assert data["url"] == payload["url"]
    assert data["method"] == "POST"
    assert data["hasSecret"] is True
    # Crucial security guarantee: raw secret must never appear in response
    assert "secret" not in data
    assert "sk_test" not in str(data)

    # Verify database persistence & encryption
    api = db_session.scalar(select(ApiEndpoint).where(ApiEndpoint.id == data["id"]))
    assert api is not None
    assert api.encrypted_secret is not None
    assert "sk_test" not in api.encrypted_secret
    assert decrypt_credential(api.encrypted_secret) == "sk_test_super_secret_key_12345"


def test_create_api_unauthenticated(client: TestClient):
    """Unauthenticated API creation is rejected with 401."""
    resp = client.post("/api/v1/apis", json=sample_api_payload())
    assert resp.status_code == 401


def test_list_apis_scoped_to_user(
    authenticated_client: TestClient,
    auth_headers: dict,
    db_session: Session,
    other_user: User,
):
    """Listing APIs returns only APIs owned by the authenticated user."""
    # Create an API for authenticated user
    resp1 = authenticated_client.post(
        "/api/v1/apis",
        json=sample_api_payload(),
        headers=auth_headers,
    )
    assert resp1.status_code == 201
    my_api_id = resp1.json()["id"]

    # Create an API directly in DB for other_user
    other_api = ApiEndpoint(
        user_id=other_user.id,
        name="Other User Private API",
        url="https://api.github.com/user",
        method="GET",
        query_params=[],
        headers=[],
        auth_type="none",
        expected_status=200,
    )
    db_session.add(other_api)
    db_session.commit()

    # List APIs as authenticated user
    list_resp = authenticated_client.get("/api/v1/apis")
    assert list_resp.status_code == 200
    apis = list_resp.json()
    api_ids = [a["id"] for a in apis]

    assert my_api_id in api_ids
    assert other_api.id not in api_ids


def test_get_api_cross_user_returns_404(
    authenticated_client: TestClient,
    db_session: Session,
    other_user: User,
):
    """Accessing another user's API returns 404, preventing information leakage."""
    other_api = ApiEndpoint(
        user_id=other_user.id,
        name="Other User API",
        url="https://api.example.com",
        method="GET",
        query_params=[],
        headers=[],
        auth_type="none",
        expected_status=200,
    )
    db_session.add(other_api)
    db_session.commit()

    resp = authenticated_client.get(f"/api/v1/apis/{other_api.id}")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"



def test_update_api_omitted_secret_preserves_existing(
    authenticated_client: TestClient,
    auth_headers: dict,
    db_session: Session,
):
    """Updating API with omitted secret field must not erase the existing secret."""
    # Create with secret
    create_resp = authenticated_client.post(
        "/api/v1/apis",
        json=sample_api_payload(),
        headers=auth_headers,
    )
    api_id = create_resp.json()["id"]

    # Patch with only name update, omitting secret
    patch_resp = authenticated_client.patch(
        f"/api/v1/apis/{api_id}",
        json={"name": "Renamed Payment Gateway"},
        headers=auth_headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["name"] == "Renamed Payment Gateway"
    assert patch_resp.json()["hasSecret"] is True

    # Check DB still has original encrypted secret
    api = db_session.scalar(select(ApiEndpoint).where(ApiEndpoint.id == api_id))
    assert api is not None
    assert decrypt_credential(api.encrypted_secret) == "sk_test_super_secret_key_12345"


def test_update_api_replace_secret(
    authenticated_client: TestClient,
    auth_headers: dict,
    db_session: Session,
):
    """Updating API with a new secret replaces the encrypted value."""
    create_resp = authenticated_client.post(
        "/api/v1/apis",
        json=sample_api_payload(),
        headers=auth_headers,
    )
    api_id = create_resp.json()["id"]

    patch_resp = authenticated_client.patch(
        f"/api/v1/apis/{api_id}",
        json={"secret": "new_secret_key_99999"},
        headers=auth_headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["hasSecret"] is True

    api = db_session.scalar(select(ApiEndpoint).where(ApiEndpoint.id == api_id))
    assert api is not None
    assert decrypt_credential(api.encrypted_secret) == "new_secret_key_99999"


def test_update_api_remove_secret(
    authenticated_client: TestClient,
    auth_headers: dict,
    db_session: Session,
):
    """Switching authType to 'none' or setting secret to '' clears the encrypted secret."""
    create_resp = authenticated_client.post(
        "/api/v1/apis",
        json=sample_api_payload(),
        headers=auth_headers,
    )
    api_id = create_resp.json()["id"]

    patch_resp = authenticated_client.patch(
        f"/api/v1/apis/{api_id}",
        json={"authType": "none", "secret": ""},
        headers=auth_headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["hasSecret"] is False

    api = db_session.scalar(select(ApiEndpoint).where(ApiEndpoint.id == api_id))
    assert api is not None
    assert api.encrypted_secret is None


def test_delete_api_returns_204(
    authenticated_client: TestClient,
    auth_headers: dict,
    db_session: Session,
):
    """Deleting an owned API returns empty 204 No Content and removes it from DB."""
    create_resp = authenticated_client.post(
        "/api/v1/apis",
        json=sample_api_payload(),
        headers=auth_headers,
    )
    api_id = create_resp.json()["id"]

    del_resp = authenticated_client.delete(
        f"/api/v1/apis/{api_id}",
        headers=auth_headers,
    )
    assert del_resp.status_code == 204
    assert del_resp.content == b""

    # Verify record is deleted
    api = db_session.scalar(select(ApiEndpoint).where(ApiEndpoint.id == api_id))
    assert api is None

    # Deleting again returns 404
    del_again = authenticated_client.delete(
        f"/api/v1/apis/{api_id}",
        headers=auth_headers,
    )
    assert del_again.status_code == 404
