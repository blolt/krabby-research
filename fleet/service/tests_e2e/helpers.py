"""Shared helpers for fleet service live E2E tests (Cognito scratch users, etc.)."""
from __future__ import annotations

import os
import secrets
from typing import Iterator

import boto3
from pycognito import Cognito

AWS_REGION = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
COGNITO_USER_POOL_ID = os.environ.get("COGNITO_USER_POOL_ID", "")
COGNITO_APP_CLIENT_ID = os.environ.get("COGNITO_APP_CLIENT_ID", "")


def cognito_idp():
    return boto3.client("cognito-idp", region_name=AWS_REGION)


def scratch_user(operator: bool) -> Iterator[Cognito]:
    """Create a throwaway Cognito user; yield authenticated session; delete on exit."""
    idp = cognito_idp()
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
    idp.admin_set_user_password(
        UserPoolId=COGNITO_USER_POOL_ID,
        Username=username,
        Password=password,
        Permanent=True,
    )
    if operator:
        idp.admin_add_user_to_group(
            UserPoolId=COGNITO_USER_POOL_ID,
            Username=username,
            GroupName="operator",
        )

    try:
        user = Cognito(COGNITO_USER_POOL_ID, COGNITO_APP_CLIENT_ID, username=username)
        user.authenticate(password=password)
        yield user
    finally:
        idp.admin_delete_user(UserPoolId=COGNITO_USER_POOL_ID, Username=username)
