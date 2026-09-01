# Fleet service live E2E (SSH + teleop)

Tests against a **deployed** fleet host and an enrolled bench Orin. Non-secret
settings come from committed [`../config/fleet.toml`](../config/fleet.toml)
(see [`../config/README.md`](../config/README.md)).

## When tests run

| Context | Behavior |
|---------|----------|
| Local `pytest tests_e2e/` (default) | **Skipped** — unit runs stay green |
| `BENCH_E2E=1` or GitHub Actions | **Pass/fail** — missing config, password, tools, or bench → red job |

## Config vs secrets

| Source | What |
|--------|------|
| `fleet/config/fleet.toml` | URLs, region, Cognito pool/client IDs, bench thing name, CI operator email |
| GitHub secret `COGNITO_CI_PASSWORD` | CI operator password only |
| Env vars | Optional overrides of any committed value |

## CI scope

**Happy path only**: list devices, SSH tunnel, teleop signaling/video/control, authed
ICE servers. Uses the persistent CI operator (`[ci].operator_username` +
`COGNITO_CI_PASSWORD`) — no scratch Cognito users, no negative-auth cases.

Teleop also needs runner AWS creds with `iot:DescribeEndpoint` and MQTT SigV4 on
`teleop/*/signaling/*` (signaling sniffer).

Bench preconditions for teleop:

* `krabby agent` running (shadow + tunnels + teleop shim on `:9000`)
* HAL edge with `--teleop-ip 127.0.0.1` (and camera available), plus
  `--teleop-control-echo` for the HAL-ack assertion in `test_teleop_e2e.py`

## Run

```bash
cd fleet/service
python3 -m venv .venv && source .venv/bin/activate
pip install -e ../config -e ".[e2e]"
playwright install --with-deps chromium

export COGNITO_CI_PASSWORD='…'   # CI operator password
export BENCH_E2E=1

pytest tests_e2e/ -q
```

SSH round-trip also needs `krabby-fleet` CLI and `localproxy` on PATH.

## Coverage

| Test | Checks |
|------|--------|
| `test_open_and_close_tunnel_happy_path` | Operator opens/closes SSH tunnel via REST |
| `test_get_devices_*` | List + get device shadow for bench |
| `test_krabby_fleet_ssh_runs_command_end_to_end` | CLI SSH echo through Secure Tunnel |
| `test_teleop_signaling_control_and_video` | Portal viewer → Playing; control + video; MQTT idle after close |
| `test_teleop_ice_servers_authed` | ICE endpoint returns STUN with operator token |
