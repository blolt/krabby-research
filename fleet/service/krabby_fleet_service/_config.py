"""Runtime settings: Cognito user pool / app client, read from SSM at startup.

The EC2 instance this service runs on has its own IAM role (granted by
`FleetServiceStack`) with read access to these parameters -- no static AWS
credentials needed. Env var overrides exist for local dev/tests so nothing
here requires real AWS access to run.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

AWS_REGION = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"

# Must match fleet/infra/fleet_service_stack.py's COGNITO_USER_POOL_ID_PARAM_NAME /
# COGNITO_APP_CLIENT_ID_PARAM_NAME -- keep the two in sync if either changes.
COGNITO_USER_POOL_ID_PARAM = "/krabby/fleet/cognito-user-pool-id"
COGNITO_APP_CLIENT_ID_PARAM = "/krabby/fleet/cognito-app-client-id"


@dataclass(frozen=True)
class Settings:
    aws_region: str
    cognito_user_pool_id: str
    cognito_app_client_id: str

    @property
    def cognito_issuer(self) -> str:
        return f"https://cognito-idp.{self.aws_region}.amazonaws.com/{self.cognito_user_pool_id}"

    @property
    def cognito_jwks_url(self) -> str:
        return f"{self.cognito_issuer}/.well-known/jwks.json"


def _ssm_parameter(name: str) -> str:
    import boto3

    client = boto3.client("ssm", region_name=AWS_REGION)
    return client.get_parameter(Name=name)["Parameter"]["Value"]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    user_pool_id = os.environ.get("KRABBY_FLEET_COGNITO_USER_POOL_ID") or _ssm_parameter(
        COGNITO_USER_POOL_ID_PARAM
    )
    app_client_id = os.environ.get("KRABBY_FLEET_COGNITO_APP_CLIENT_ID") or _ssm_parameter(
        COGNITO_APP_CLIENT_ID_PARAM
    )
    return Settings(
        aws_region=AWS_REGION,
        cognito_user_pool_id=user_pool_id,
        cognito_app_client_id=app_client_id,
    )
