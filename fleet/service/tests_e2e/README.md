# Fleet service live E2E (SSH + teleop)

Tests against a **deployed** fleet host and Bruce's enrolled bench Orin
(`bench-krabby-ci`). Skipped unless the env below is set — unit `pytest tests/`
without a live environment stays green.

## Env

| Variable | Required for | Notes |
|----------|--------------|-------|
| `FLEET_SERVICE_URL` | SSH + teleop | e.g. `https://fleet.example.com/api` |
| `FLEET_PORTAL_URL` | teleop | e.g. `https://fleet.example.com` (no `/api`) |
| `COGNITO_USER_POOL_ID` | both | From `FleetServiceStack` |
| `COGNITO_APP_CLIENT_ID` | both | From `FleetServiceStack` |
| `AWS_REGION` | both | Default `us-east-1` |
| `BENCH_E2E=1` | teleop | Explicit enable for Playwright suite |
| `BENCH_THING_NAME` | both | Default `bench-krabby-ci` |

AWS credentials (default chain) need Cognito admin APIs for scratch users, plus
`iot:DescribeEndpoint` and MQTT SigV4 `Connect`/`Subscribe`/`Receive` on
`teleop/*/signaling/*` for the teleop signaling sniffer (mirror the fleet
instance role's teleop IAM, or grant the CI OIDC role the same).

Bench preconditions for teleop:

* `krabby agent` running (shadow + tunnels + teleop shim on `:9000`)
* HAL edge with `--teleop-ip 127.0.0.1` (and camera available), plus
  `--teleop-control-echo` for the HAL-ack assertion in
  `test_teleop_e2e.py`

## Run

```bash
cd fleet/service
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[e2e]"
playwright install --with-deps chromium

export FLEET_SERVICE_URL=https://{fleet-domain}/api
export FLEET_PORTAL_URL=https://{fleet-domain}
export COGNITO_USER_POOL_ID=...
export COGNITO_APP_CLIENT_ID=...
export AWS_REGION=us-east-1
export BENCH_E2E=1

pytest tests_e2e/ -q
```

SSH-only (no Playwright / no `BENCH_E2E`):

```bash
pytest tests_e2e/test_ssh_tunnel_e2e.py -q
```

## Teleop coverage

| Test | Checks |
|------|--------|
| `test_teleop_signaling_control_and_video` | Cognito → viewer → Playing; MQTT `signaling/*` activity; control DC + motion-safe zero payload; ≥1 video track; MQTT idle after close |
| `test_teleop_unauthenticated_signaling_rejected` | WS without token fails; no `signaling/in` publish |
| `test_teleop_ice_servers_*` | ICE endpoint 401 anon / 200 + STUN with operator token |
