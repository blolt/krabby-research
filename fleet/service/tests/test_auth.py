"""require_operator: JWT verification + operator-group gate.

No real Cognito/network access -- tokens are signed locally with a
throwaway RSA keypair, and JWKS resolution is patched to hand back that
keypair's public half directly instead of fetching a real JWKS document.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from krabby_fleet_service._auth import require_operator
from krabby_fleet_service._config import Settings, get_settings

_SETTINGS = Settings(
    aws_region="us-east-1",
    cognito_user_pool_id="us-east-1_TESTPOOL",
    cognito_app_client_id="test-client-id",
    iot_ats_endpoint="example-ats.iot.us-east-1.amazonaws.com",
)


@pytest.fixture(scope="module")
def keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


def _token(keypair, **overrides) -> str:
    private_key, _ = keypair
    now = int(time.time())
    claims = {
        "iss": _SETTINGS.cognito_issuer,
        "token_use": "access",
        "client_id": _SETTINGS.cognito_app_client_id,
        "cognito:groups": ["operator"],
        "iat": now,
        "exp": now + 3600,
        **overrides,
    }
    return jwt.encode(claims, private_key, algorithm="RS256")


@pytest.fixture
def app(keypair):
    _, public_key = keypair
    test_app = FastAPI()

    @test_app.get("/protected")
    def protected(claims: dict = Depends(require_operator)):
        return {"ok": True}

    test_app.dependency_overrides[get_settings] = lambda: _SETTINGS

    fake_jwks_client = MagicMock()
    fake_jwks_client.get_signing_key_from_jwt.return_value = MagicMock(key=public_key)
    with patch("krabby_fleet_service._auth._jwks_client", return_value=fake_jwks_client):
        yield test_app

    test_app.dependency_overrides.clear()


def test_valid_operator_token_succeeds(app, keypair):
    resp = TestClient(app).get(
        "/protected", headers={"Authorization": f"Bearer {_token(keypair)}"}
    )
    assert resp.status_code == 200


def test_missing_token_is_401(app):
    resp = TestClient(app).get("/protected")
    assert resp.status_code == 401


def test_malformed_auth_header_is_401(app):
    resp = TestClient(app).get("/protected", headers={"Authorization": "not-a-bearer-token"})
    assert resp.status_code == 401


def test_expired_token_is_401(app, keypair):
    token = _token(keypair, exp=int(time.time()) - 10)
    resp = TestClient(app).get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_wrong_issuer_is_401(app, keypair):
    token = _token(keypair, iss="https://cognito-idp.us-east-1.amazonaws.com/us-east-1_OTHERPOOL")
    resp = TestClient(app).get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_wrong_client_id_is_401(app, keypair):
    token = _token(keypair, client_id="some-other-client")
    resp = TestClient(app).get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_non_access_token_is_401(app, keypair):
    token = _token(keypair, token_use="id")
    resp = TestClient(app).get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_non_operator_group_is_403(app, keypair):
    token = _token(keypair, **{"cognito:groups": ["viewer"]})
    resp = TestClient(app).get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_no_groups_claim_is_403(app, keypair):
    token = _token(keypair, **{"cognito:groups": []})
    resp = TestClient(app).get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403
