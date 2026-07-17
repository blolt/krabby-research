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
  BENCH_SSH_USER          defaults to operator

AWS credentials come from the environment's default boto3 credential chain
and need Cognito admin permissions on the user pool above:
AdminCreateUser, AdminSetUserPassword, AdminAddUserToGroup, AdminDeleteUser.

Every test here is skipped (not failed) when FLEET_SERVICE_URL,
COGNITO_USER_POOL_ID, or COGNITO_APP_CLIENT_ID aren't set, so `pytest`
without a deployed environment to point at doesn't fail here.

The live round-trip test additionally needs the `krabby-fleet` CLI
(krabby-fleet-cli, this repo's fleet/cli) and the `localproxy` binary
(aws-iot-securetunneling-localproxy) on PATH -- it's skipped, not failed,
when either is missing, same as the env vars above. It also needs a key for
BENCH_SSH_USER already loaded in the runner's SSH agent; that one is a real
precondition on the deployed environment (the CLI's own `ssh` invocation
tries pubkey auth first), so a missing key surfaces as a hang-until-timeout
on the interactive password prompt rather than a skip.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import subprocess
import time
from pathlib import Path
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
BENCH_SSH_USER = os.environ.get("BENCH_SSH_USER", "operator")

_CLI_BIN = "krabby-fleet"
_LOCALPROXY_BIN = "localproxy"

# Real dotfiles the krabby-fleet CLI reads -- see fleet/cli/krabby_fleet_cli/
# _config.py (CONFIG_PATH) and _auth.py (SESSION_PATH). The CLI has no env
# var override for either, so the only way to drive it as a real,
# non-interactive subprocess is to write these for real and restore
# whatever (if anything) was there before.
_CLI_CONFIG_PATH = Path.home() / ".config" / "krabby-fleet" / "config.toml"
_CLI_SESSION_PATH = Path.home() / ".config" / "krabby-fleet" / "session.json"

pytestmark = pytest.mark.skipif(
    not (FLEET_SERVICE_URL and COGNITO_USER_POOL_ID and COGNITO_APP_CLIENT_ID),
    reason="FLEET_SERVICE_URL / COGNITO_USER_POOL_ID / COGNITO_APP_CLIENT_ID not set",
)


def _cognito_idp():
    return boto3.client("cognito-idp", region_name=AWS_REGION)


def _scratch_user(operator: bool) -> Iterator[Cognito]:
    """Creates a throwaway, immediately-usable Cognito user (in the operator
    group if `operator`), yields the authenticated Cognito session for it,
    deletes the user on teardown."""
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
        yield user
    finally:
        idp.admin_delete_user(UserPoolId=COGNITO_USER_POOL_ID, Username=username)


@pytest.fixture
def operator_token() -> Iterator[str]:
    for user in _scratch_user(operator=True):
        yield user.access_token


@pytest.fixture
def non_operator_token() -> Iterator[str]:
    for user in _scratch_user(operator=False):
        yield user.access_token


@pytest.fixture
def operator_session() -> Iterator[Cognito]:
    yield from _scratch_user(operator=True)


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


def test_get_devices_lists_bench_robot(operator_token):
    resp = requests.get(
        f"{FLEET_SERVICE_URL}/devices",
        headers={"Authorization": f"Bearer {operator_token}"},
        timeout=30,
    )
    assert resp.status_code == 200, resp.text
    thing_names = {device["thingName"] for device in resp.json()}
    assert BENCH_THING_NAME in thing_names


def test_get_devices_without_token_is_401():
    resp = requests.get(f"{FLEET_SERVICE_URL}/devices", timeout=30)
    assert resp.status_code == 401


def test_get_device_returns_bench_shadow(operator_token):
    resp = requests.get(
        f"{FLEET_SERVICE_URL}/devices/{BENCH_THING_NAME}",
        headers={"Authorization": f"Bearer {operator_token}"},
        timeout=30,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["thingName"] == BENCH_THING_NAME
    assert "connected" in body
    assert isinstance(body.get("reported"), dict)
    reported = body["reported"]
    assert reported.get("timestamp"), "expected recent shadow reported.timestamp from bench agent"
    assert time.time() - int(reported["timestamp"]) < 300, (
        "shadow reported.timestamp should be within the last 5 minutes"
    )


def test_get_device_without_token_is_401():
    resp = requests.get(f"{FLEET_SERVICE_URL}/devices/{BENCH_THING_NAME}", timeout=30)
    assert resp.status_code == 401


@pytest.fixture
def cli_operator_session(operator_session: Cognito) -> Iterator[None]:
    """Writes real ~/.config/krabby-fleet/{config.toml,session.json} for the
    scratch operator user, so a `krabby-fleet` subprocess authenticates with
    no interactive prompt. Backs up and restores whatever was there."""
    config_backup = _CLI_CONFIG_PATH.read_text() if _CLI_CONFIG_PATH.exists() else None
    session_backup = _CLI_SESSION_PATH.read_text() if _CLI_SESSION_PATH.exists() else None
    _CLI_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

    _CLI_CONFIG_PATH.write_text(
        "[fleet]\n"
        f'service_url = "{FLEET_SERVICE_URL}"\n\n'
        "[cognito]\n"
        f'user_pool_id = "{COGNITO_USER_POOL_ID}"\n'
        f'client_id = "{COGNITO_APP_CLIENT_ID}"\n\n'
        "[ssh]\n"
        f'default_user = "{BENCH_SSH_USER}"\n'
    )
    _CLI_SESSION_PATH.write_text(
        json.dumps(
            {
                "access_token": operator_session.access_token,
                "id_token": operator_session.id_token,
                "refresh_token": operator_session.refresh_token,
            }
        )
    )
    _CLI_SESSION_PATH.chmod(0o600)

    try:
        yield
    finally:
        if config_backup is not None:
            _CLI_CONFIG_PATH.write_text(config_backup)
        else:
            _CLI_CONFIG_PATH.unlink(missing_ok=True)
        if session_backup is not None:
            _CLI_SESSION_PATH.write_text(session_backup)
        else:
            _CLI_SESSION_PATH.unlink(missing_ok=True)


@pytest.mark.skipif(
    not (shutil.which(_CLI_BIN) and shutil.which(_LOCALPROXY_BIN)),
    reason="krabby-fleet CLI and/or localproxy not installed",
)
def test_krabby_fleet_ssh_runs_command_end_to_end(cli_operator_session):
    result = subprocess.run(
        [_CLI_BIN, "ssh", BENCH_THING_NAME],
        input="echo hello\nexit\n",
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert "hello" in result.stdout, result.stdout + result.stderr

    match = re.search(r"tunnel (\S+) open", result.stdout)
    assert match, f"couldn't find tunnel ID in CLI output:\n{result.stdout}"
    tunnel_id = match.group(1)

    # The destination-side localproxy on the robot (spawned by `krabby
    # agent`, see krabby/agent.py) has no explicit "close" signal -- it
    # exits on its own when AWS tears the tunnel down, reaped after the
    # fact. `close_ssh_tunnel` uses `delete=True`, which removes the tunnel
    # record entirely, so a post-close DescribeTunnel raising
    # ResourceNotFoundException is the observable proxy for "AWS actually
    # tore this down" from outside the robot itself.
    tunneling = boto3.client("iotsecuretunneling", region_name=AWS_REGION)
    with pytest.raises(tunneling.exceptions.ResourceNotFoundException):
        tunneling.describe_tunnel(tunnelId=tunnel_id)
