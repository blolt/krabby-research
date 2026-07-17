# Fleet setup and operations

Operator guide for the Krabby fleet: AWS IoT control plane, device
onboarding, telemetry, and the fleet service stack.

Infra deploy scripts live under [`infra/`](infra/README.md).

## Deploy sequence (fresh account)

1. Deploy the control plane (IoT thing type, per-thing policy, Fleet Indexing,
   reported-images bucket):

   ```bash
   cd fleet/infra
   ./scripts/setup-venv.sh
   source .venv/bin/activate
   ./scripts/deploy-control-plane.sh
   ```

2. Deploy the fleet service stack (EC2, Cognito, tunnel API — see
   [`infra/fleet-service.md`](infra/fleet-service.md)):

   ```bash
   ./scripts/deploy-fleet-service.sh
   ```

3. On each robot Orin, enroll the device (operator-run, needs sudo + AWS creds):

   ```bash
   sudo krabby enroll --thing-name <name>
   sudo systemctl start krabby-agent
   ```

4. Verify shadow telemetry:

   ```bash
   krabby get telemetry
   aws iot-data get-thing-shadow --thing-name <name> /dev/stdout | jq '.state.reported'
   curl -H "Authorization: Bearer <token>" https://<fleet-host>/api/devices
   curl -H "Authorization: Bearer <token>" https://<fleet-host>/api/devices/<name>
   ```

## MQTT topic scheme

| Topic | Direction | Purpose |
|-------|-----------|---------|
| `$aws/things/{thingName}/shadow/update` | device → cloud | 1/min fleet telemetry in `state.reported` |
| `teleop/{thingName}/signaling/in` | cloud → device | WebRTC signaling |
| `teleop/{thingName}/signaling/out` | device → cloud | WebRTC signaling |
| `$aws/things/{thingName}/tunnels/notify` | cloud → device | Secure Tunneling destination token (reserved) |

Per-thing isolation is enforced by `KrabDevicePolicy` using
`${iot:Connection.Thing.ThingName}` — a device cert cannot publish or
subscribe on another device's topics.

## Bench control-plane E2E

Automated control-plane checks against the permanently enrolled bench Orin
(`bench-krabby-ci` by default): connectivity + shadow via Fleet Indexing /
`GetThingShadow`, per-thing isolation with a scratch cert, and Secure
Tunneling TCP through source `localproxy`. See
[`infra/tests_e2e/README.md`](infra/tests_e2e/README.md).

```bash
export BENCH_E2E=1
cd fleet/infra && source .venv/bin/activate
pip install -r tests_e2e/requirements.txt
pytest tests_e2e/ -q
```

## Runtime (EC2)

One host runs three systemd units (plus coturn for teleop TURN), all logging to
journald:

| Unit | Bind | Role |
|------|------|------|
| `krabby-fleet-service` | `127.0.0.1:8080` | Fleet REST API |
| `krabby-fleet-portal` | `127.0.0.1:3000` | Next.js operator UI + NextAuth |
| `caddy` | `:443` / `:80` | TLS + reverse proxy |

Caddy routing (`fleet/service/deploy/Caddyfile`):

- `/api/auth*` → portal (NextAuth)
- `/api/*` → fleet service (strip `/api` prefix)
- everything else → portal

```bash
journalctl -u krabby-fleet-service -f
journalctl -u krabby-fleet-portal -f
journalctl -u caddy -f
```

Deploy both apps with `fleet/infra/scripts/deploy-fleet-service.sh` (CDK + SSM).

## Fleet service API

Caddy serves the fleet service under `/api/*` (prefix stripped), except
`/api/auth*` which is reverse-proxied to the Next.js portal (NextAuth).
All fleet-service routes except `/healthz` require a Cognito access token
for a user in the `operator` group.

| Method | Path | Backend |
|--------|------|---------|
| `GET` | `/devices` | `iot:SearchIndex` (`thingTypeName:Krab`) — connectivity + shadow `reported` |
| `GET` | `/devices/{thingName}` | `iot:DescribeThing` + `iot:GetThingShadow` + SearchIndex connectivity |
| `POST` | `/devices/{thingName}/ssh-tunnel` | `iotsecuretunneling:OpenTunnel` |
| `DELETE` | `/devices/{thingName}/ssh-tunnel/{tunnelId}` | `iotsecuretunneling:CloseTunnel` |

## Portal + CLI

- Portal: [`portal/`](portal/README.md) — Cognito sign-in, device list/detail, Open SSH.
- CLI: `krabby-fleet list` prints online/last-seen + telemetry summary (same `GET /devices` data).

## Telemetry

### Topic and rate

`krabby agent` publishes once per minute to the device's Classic Shadow:

```json
{"state": {"reported": { ... }}}
```

The fleet portal and `krabby-fleet list` read the latest document via Fleet
Indexing (`iot:SearchIndex`) or `iot:GetThingShadow`.

### Schema (open-ended)

There is **no fixed JSON Schema** for `state.reported`. The canonical source
of truth on the device is:

```bash
krabby get telemetry
```

Whatever that command prints is what `krabby agent` uploads to the shadow on
the next 1/min tick. New fields may appear as the locomotion stack and host
expose more signals; consumers should treat unknown keys as opaque.

### Typical top-level keys

These fields are populated when the underlying source is available:

| Key | Source | Notes |
|-----|--------|-------|
| `timestamp` | wall clock | Unix epoch seconds |
| `reported_image` | `~/.config/krabby/state.json` | Running locomotion image ref from `krabby install` / `krabby update`. May later become an S3 object reference for a camera snapshot (`KrabReportedImages` bucket). |
| `health` | host | `locomotion_container`, `krabby_agent`, `krabby_locomotion` systemd states, `mcu_present` |
| `imu` | HAL (locomotion container) | `base_quat_w`, `base_ang_vel_b`, `base_lin_vel_b` when the HAL server is publishing observations |
| `pose` | HAL | `joint_positions`, `joint_velocities` |
| `power` | sysfs | `supplies[]` with `capacity_percent`, `voltage_v`, `current_a` when exposed by the board |
| `red_flags` | derived | Strings such as `agent_not_running`, `locomotion_container_down`, `hal_no_observation`, `mcu_missing` |

Example (fields vary by runtime state):

```json
{
  "timestamp": 1710000000,
  "reported_image": "public.ecr.aws/t7t7b3i3/krabby-locomotion:release-latest",
  "health": {
    "locomotion_container": "running",
    "krabby_agent": "active",
    "krabby_locomotion": "active",
    "mcu_present": true
  },
  "imu": {
    "base_quat_w": [0.0, 0.0, 0.0, 1.0],
    "base_ang_vel_b": [0.0, 0.0, 0.0],
    "base_lin_vel_b": [0.0, 0.0, 0.0]
  },
  "pose": {
    "joint_positions": [0.1, 0.2],
    "joint_velocities": [0.0, 0.0]
  },
  "power": {
    "supplies": [{"name": "BAT0", "capacity_percent": 87}]
  },
  "red_flags": []
}
```

### `reported_image`

Today this is the installed locomotion image tag/ref. Camera frame uploads to
the `KrabReportedImages` S3 bucket (via the `KrabImageRoleAlias` credentials
provider) are infrastructure-ready in `ControlPlaneStack` but not yet wired
into the agent — when added, `reported_image` will hold an S3 URI instead of
inline image bytes (shadow documents must stay small).

## Device services

| Unit | Started by | Role |
|------|------------|------|
| `krabby-locomotion.service` | `krabby install` | Runs `krabby run` (HAL + controller container) |
| `krabby-agent.service` | `krabby enroll` | Runs `krabby agent` (MQTT shadow + tunnel notify) |

Logs:

```bash
journalctl -u krabby-agent -f
journalctl -u krabby-locomotion -f
```

## Troubleshooting

| Symptom | Check |
|---------|-------|
| Shadow `timestamp` stale | `systemctl status krabby-agent`; `journalctl -u krabby-agent` |
| Empty `imu` / `pose` | `docker ps` shows `krabby` running; HAL publishing on `:6001` |
| `red_flags` includes `mcu_missing` | USB hub + `/dev/ttyACM0` present |
| Enroll fails on policy | Deploy `ControlPlaneStack` first |
| Tunnel SSH fails | `localproxy` installed (`krabby enroll`); agent subscribed to `tunnels/notify` |

## Rollback

Redeploy CDK at a prior git SHA:

```bash
git checkout <sha>
cd fleet/infra && source .venv/bin/activate
./scripts/deploy-control-plane.sh
./scripts/deploy-fleet-service.sh
```

SSM restart on the fleet EC2 picks up new service artifacts after
`fleet-deploy.yml` runs.
