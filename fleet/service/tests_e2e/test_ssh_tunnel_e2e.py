"""SSH tunnel auth E2E test: real Cognito, real fleet service, real bench robot.

Unlike tests/ (mocked, no external access), everything here is a real network
call: `boto3` admin Cognito operations, real SRP login via `pycognito`, and
real HTTP requests to a deployed fleet service backed by real Secure
Tunneling calls against a real, enrolled robot. Configured entirely by env
vars, no config file:

  FLEET_SERVICE_URL      e.g. https://fleet.example.com/api
  COGNITO_USER_POOL_ID
  COGNITO_APP_CLIENT_ID
  AWS_REGION             (or AWS_DEFAULT_REGION) -- defaults to us-east-1
  BENCH_THING_NAME        defaults to bench-krabby-ci

AWS credentials come from the environment's default boto3 credential chain
and need Cognito admin permissions on the user pool above:
AdminCreateUser, AdminSetUserPassword, AdminAddUserToGroup, AdminDeleteUser.

Every test here is skipped (not failed) when FLEET_SERVICE_URL,
COGNITO_USER_POOL_ID, or COGNITO_APP_CLIENT_ID aren't set, so `pytest`
without a deployed environment to point at doesn't fail here.
"""
from __future__ import annotations

import os
import secrets
from typing import Iterator

import boto3
import pytest
import requests
from pycognito import Cognito

FLEET_SERVICE_URL = os.environ.get("FLEET_SERVICE_URL", "").rstrip("/")
COGNITO_USER_POOL_ID = os.environ.get("COGNITO_USER_POOL_ID", "")
COGNITO_APP_CLIENT_ID = os.environ.get("COGNITO_APP_CLIENT_ID", "")
AWS_REGION = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
BENCH_THING_NAME = os.environ.get("BENCH_THING_NAME", "bench-krabby-ci")

pytestmark = pytest.mark.skipif(
    not (FLEET_SERVICE_URL and COGNITO_USER_POOL_ID and COGNITO_APP_CLIENT_ID),
    reason="FLEET_SERVICE_URL / COGNITO_USER_POOL_ID / COGNITO_APP_CLIENT_ID not set",
)


def _cognito_idp():
    return boto3.client("cognito-idp", region_name=AWS_REGION)


def _scratch_user(operator: bool) -> Iterator[str]:
    """Creates a throwaway, immediately-usable Cognito user (in the operator
    group if `operator`), yields a real access token for it, deletes the
    user on teardown."""
    idp = _cognito_idp()
    username = f"e2e-test-{secrets.token_hex(6)}"
    password = f"E2eTest!{secrets.token_hex(8)}"

    idp.admin_create_user(
        UserPoolId=COGNITO_USER_POOL_ID,
        Username=username,
        UserAttributes=[
            {"Name": "email", "Value": f"{username}@example.invalid"},
            {"Name": "email_verified", "Value": "true"},
        ],
        MessageAction="SUPPRESS",
        TemporaryPassword=password,
    )
    # Immediately promotes the user out of FORCE_CHANGE_PASSWORD into
    # CONFIRMED with a permanent password, so SRP auth works right away --
    # no email/SMS verification round-trip needed for a scratch test user.
    idp.admin_set_user_password(
        UserPoolId=COGNITO_USER_POOL_ID, Username=username, Password=password, Permanent=True,
    )
    if operator:
        idp.admin_add_user_to_group(
            UserPoolId=COGNITO_USER_POOL_ID, Username=username, GroupName="operator",
        )

    try:
        user = Cognito(COGNITO_USER_POOL_ID, COGNITO_APP_CLIENT_ID, username=username)
        user.authenticate(password=password)
        yield user.access_token
    finally:
        idp.admin_delete_user(UserPoolId=COGNITO_USER_POOL_ID, Username=username)


@pytest.fixture
def operator_token() -> Iterator[str]:
    yield from _scratch_user(operator=True)


@pytest.fixture
def non_operator_token() -> Iterator[str]:
    yield from _scratch_user(operator=False)


def test_open_and_close_tunnel_happy_path(operator_token):
    resp = requests.post(
        f"{FLEET_SERVICE_URL}/devices/{BENCH_THING_NAME}/ssh-tunnel",
        headers={"Authorization": f"Bearer {operator_token}"},
        timeout=30,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tunnelId"]
    assert body["sourceAccessToken"]
    assert body["region"]

    close_resp = requests.delete(
        f"{FLEET_SERVICE_URL}/devices/{BENCH_THING_NAME}/ssh-tunnel/{body['tunnelId']}",
        headers={"Authorization": f"Bearer {operator_token}"},
        timeout=30,
    )
    assert close_resp.status_code == 204


def test_open_tunnel_without_token_is_401():
    resp = requests.post(
        f"{FLEET_SERVICE_URL}/devices/{BENCH_THING_NAME}/ssh-tunnel", timeout=30,
    )
    assert resp.status_code == 401


def test_open_tunnel_without_operator_group_is_403(non_operator_token):
    resp = requests.post(
        f"{FLEET_SERVICE_URL}/devices/{BENCH_THING_NAME}/ssh-tunnel",
        headers={"Authorization": f"Bearer {non_operator_token}"},
        timeout=30,
    )
    assert resp.status_code == 403
