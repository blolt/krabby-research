"""GET /devices: mocked iot client, no real AWS calls.

Overrides the require_operator dependency directly, same as test_tunnels.py,
to stay focused on the fleet-listing logic rather than re-deriving auth
coverage.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from krabby_fleet_service._auth import require_operator
from krabby_fleet_service._config import Settings, get_settings
from krabby_fleet_service.app import app

_SETTINGS = Settings(
    aws_region="us-east-1",
    cognito_user_pool_id="us-east-1_TESTPOOL",
    cognito_app_client_id="test-client-id",
)
_FAKE_CLAIMS = {"sub": "test-operator", "cognito:groups": ["operator"]}


@pytest.fixture
def authed_client():
    app.dependency_overrides[get_settings] = lambda: _SETTINGS
    app.dependency_overrides[require_operator] = lambda: _FAKE_CLAIMS
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def anon_client():
    app.dependency_overrides[get_settings] = lambda: _SETTINGS
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_get_devices_calls_search_index(authed_client):
    fake_client = MagicMock()
    fake_client.search_index.return_value = {
        "things": [
            {"thingName": "bench-krabby-ci", "connectivity": {"connected": True, "timestamp": 123}},
            {"thingName": "krabby-002", "connectivity": {"connected": False}},
        ],
    }
    with patch("krabby_fleet_service._devices._client", return_value=fake_client):
        resp = authed_client.get("/devices")

    assert resp.status_code == 200
    assert resp.json() == [
        {"thingName": "bench-krabby-ci", "connected": True, "connectivityTimestamp": 123},
        {"thingName": "krabby-002", "connected": False, "connectivityTimestamp": None},
    ]
    fake_client.search_index.assert_called_once_with(queryString="thingTypeName:Krab")


def test_get_devices_without_auth_is_401(anon_client):
    resp = anon_client.get("/devices")
    assert resp.status_code == 401
