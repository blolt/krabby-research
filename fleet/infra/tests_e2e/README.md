# Bench control-plane E2E

Live integration tests against an enrolled bench Orin and a real
dev-account IoT Core (`ControlPlaneStack`). Skipped unless explicitly
enabled — local `pytest` without AWS/bench stays green.

## Enable

```bash
export BENCH_E2E=1
export AWS_REGION=us-east-1          # or AWS_DEFAULT_REGION
export BENCH_THING_NAME=bench-krabby-ci   # optional; this is the default
# optional:
export SHADOW_MAX_AGE_SECS=180       # agent publishes 1/min; indexing lag
```

AWS credentials must allow: `iot:SearchIndex`, `iot:GetThingShadow`,
`iot:DescribeThing` / `CreateThing` / `DeleteThing`, cert lifecycle,
`iot:AttachPolicy` / `DetachPolicy`, `iotsecuretunneling:OpenTunnel` /
`CloseTunnel`, plus MQTT data-plane via device certs created in-test.

## Run

Use the existing infra venv (same one as CDK), then install the E2E deps:

```bash
cd fleet/infra
source .venv/bin/activate   # from ./scripts/setup-venv.sh
pip install -r tests_e2e/requirements.txt
pytest tests_e2e/ -q
```

## Coverage

| Test | Checks |
|------|--------|
| `test_control_plane_prereqs` | Persistent stack: `Krab` thing type + `KrabDevicePolicy` exist |
| `test_bench_connectivity_and_shadow_index` | `SearchIndex`: connected + recent `reported.timestamp` |
| `test_bench_get_thing_shadow_schema` | `GetThingShadow` has expected `reported` keys |
| `test_scratch_cert_cannot_update_bench_shadow` | Second-device cert cannot write bench shadow |
| `test_secure_tunnel_source_proxy_reaches_ssh` | `OpenTunnel` + source `localproxy` + SSH banner over TCP |

Bench offline or stale shadow → **red** when `BENCH_E2E=1`.
