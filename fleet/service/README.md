# krabby-fleet-service

Cognito-authenticated REST API that lets operators open/close AWS IoT Secure
Tunneling SSH sessions to fleet robots, without the browser or CLI ever
seeing AWS credentials. Runs on the `FleetServiceStack` EC2 host, using that
instance's own IAM role -- no static AWS credentials anywhere in this
service.

## Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/healthz` | none | Liveness check |
| `POST` | `/devices/{thingName}/ssh-tunnel` | operator group | Opens a Secure Tunnel (`OpenTunnel`, `services=SSH`) to the device. Returns `{tunnelId, sourceAccessToken, region}` -- the *destination* token goes straight to the device over MQTT (`krabby agent`, not through this service). |
| `DELETE` | `/devices/{thingName}/ssh-tunnel/{tunnelId}` | operator group | Force-closes the tunnel (`CloseTunnel`, `delete=True`). |

`deploy/Caddyfile` reverse-proxies `/api/*` to this service, stripping the
`/api` prefix -- the routes above are what this app itself serves, on
`127.0.0.1:8080`.

## Auth

Every non-`/healthz` route requires `Authorization: Bearer <Cognito access
token>`. The token is verified against the Cognito user pool's JWKS
(`_auth.py`): signature, issuer, `token_use=access`, and `client_id` must
all check out (401 otherwise), and the token's `cognito:groups` claim must
include `operator` (403 otherwise). Group membership is granted manually by
an admin in the Cognito console/CLI -- `FleetServiceStack` creates the empty
`operator` group but doesn't populate it.

## Configuration

Reads two values from SSM Parameter Store at startup (published by
`FleetServiceStack`; the instance role has read access):

| SSM parameter | Purpose |
|---|---|
| `/krabby/fleet/cognito-user-pool-id` | Which Cognito user pool to validate tokens against |
| `/krabby/fleet/cognito-app-client-id` | Expected `client_id` claim |

For local dev/tests, set `KRABBY_FLEET_COGNITO_USER_POOL_ID` /
`KRABBY_FLEET_COGNITO_APP_CLIENT_ID` env vars instead -- no SSM/AWS access
needed. `AWS_REGION` (or `AWS_DEFAULT_REGION`) controls both the Cognito
issuer URL and the `iotsecuretunneling` client's region; defaults to
`us-east-1`.

## Run locally

```bash
cd fleet/service
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
export KRABBY_FLEET_COGNITO_USER_POOL_ID={cognito-user-pool-id}
export KRABBY_FLEET_COGNITO_APP_CLIENT_ID={cognito-app-client-id}
export AWS_REGION={aws-region}
krabby-fleet-service   # binds 127.0.0.1:8080
```

Opening a real tunnel still needs real AWS credentials with
`iotsecuretunneling:OpenTunnel`/`CloseTunnel`/`DescribeTunnel` (the instance
role provides this in deployment; for local testing, whatever `boto3`
resolves from your environment).

## Tests

```bash
cd fleet/service
pip install -e ".[dev]"
pytest tests/
```

No real AWS or Cognito access needed -- `test_auth.py` signs test JWTs with
a locally generated RSA keypair and mocks JWKS resolution; `test_tunnels.py`
mocks the `iotsecuretunneling` boto3 client and overrides the auth
dependency directly, bypassing real JWT verification to stay focused on the
tunnel logic and the AWS calls it makes.

## Deploy artifacts

`systemd/krabby-fleet-service.service` runs `krabby-fleet-service` as a
dedicated `krabby-fleet` system user (not root -- this service needs no
special privileges). `deploy/Caddyfile` reverse-proxies `/api/*` to it.
