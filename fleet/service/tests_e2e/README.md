# Fleet service live E2E (SSH + teleop)

Tests against a **deployed** fleet host and an enrolled bench Orin. Non-secret
settings come from committed [`../config/fleet.toml`](../config/fleet.toml)
(see [`../config/README.md`](../config/README.md)). Skipped when that file is
incomplete — unit `pytest tests/` without a live environment stays green.

## Config vs secrets

| Source | What |
|--------|------|
| `fleet/config/fleet.toml` | URLs, region, Cognito pool/client IDs, bench thing name, CI operator email |
| GitHub secret `COGNITO_CI_PASSWORD` | CI operator password only (item 6 wires auth) |
| Env vars | Optional overrides of any committed value |

Fill `[cognito]` after deploy (`FleetCognitoUserPoolId` / `FleetCognitoUserPoolClientId`
stack outputs). Set `[ci].operator_username` to the CI operator email.

## Env (overrides only)

| Variable | Notes |
|----------|-------|
| `BENCH_E2E=1` | Explicit enable for Playwright teleop suite |
| `COGNITO_CI_PASSWORD` | CI operator password (secret; not in git) |
| `BENCH_SSH_USER` | Default `operator` |

AWS credentials (default chain) need Cognito admin APIs for scratch users, plus
`iot:DescribeEndpoint` and MQTT SigV4 on `teleop/*/signaling/*` for teleop
(signaling sniffer).

Bench preconditions for teleop:

* `krabby agent` running (shadow + tunnels + teleop shim on `:9000`)
* HAL edge with `--teleop-ip 127.0.0.1` (and camera available), plus
  `--teleop-control-echo` for the HAL-ack assertion in
  `test_teleop_e2e.py`

## Run

```bash
cd fleet/service
python3 -m venv .venv && source .venv/bin/activate
pip install -e ../config -e ".[e2e]"
playwright install --with-deps chromium

# Edit fleet/config/fleet.toml [cognito] first, then:
export BENCH_E2E=1   # teleop only

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
