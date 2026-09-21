# Bench Orin — always-on fleet teleop (CI / E2E)

The enrolled **bench Orin** (`bench-krabby-ci` in [`config/fleet.toml`](config/fleet.toml))
must stay ready for GitHub Actions and local `BENCH_E2E=1` runs without an
operator SSH session. That means two long-lived pieces on the robot:

| Piece | Role | How it stays up |
|-------|------|-----------------|
| **`krabby agent`** | Shadow, Secure Tunnel notify, MQTT ↔ teleop shim on **`127.0.0.1:9000`** | **`krabby-agent.service`** (systemd) |
| **Jetson HAL (fleet teleop)** | WebRTC edge dials the shim; **`--teleop-control-echo`** for E2E | **`krabby-locomotion.service`** → `krabby run` (same as [`FIELD-TELEOP.md`](FIELD-TELEOP.md)) |

On an **enrolled** bench, **`krabby run`** is fleet HAL (not gamepad). Gamepad-only
is **`krabby run --gamepad-only`**. See [`service/tests_e2e/README.md`](service/tests_e2e/README.md).

SSH pubkey setup for tunnel tests: [`BENCH-SSH.md`](BENCH-SSH.md). Device enroll:
[`ENROLL.md`](ENROLL.md).

---

## 1. Fleet agent (`krabby-launcher` ≥ 0.1.18)

Install once (PyPI) in a venv; identity lives under **`/etc/krabby/iot/`** after
enroll — **do not re-enroll** if that directory is intact.

```bash
cd ~/projects/krabs/krabby-research   # or any directory for the venv
python3 -m venv .venv-krabby
source .venv-krabby/bin/activate
pip install -U pip && pip install 'krabby-launcher>=0.1.18'

krabby --version    # expect 0.1.18+
python -c "from krabby.teleop_shim import TeleopSignalingShim; import aiohttp; print('OK')"
```

Wire systemd to this venv’s `krabby` (re-run after recreating the venv):

```bash
sudo -E env PATH="$PATH" python -c "from krabby import _iot; _iot.ensure_agent_service()"
sudo systemctl daemon-reload
sudo systemctl enable --now krabby-agent.service
```

**Verify**

```bash
systemctl is-active krabby-agent.service
sudo ss -tlnp | grep 9000    # LISTEN on 127.0.0.1:9000, owned by krabby agent
```

Agent stdout may not appear in `journalctl` until you set
`Environment=PYTHONUNBUFFERED=1` on the unit; use **`ss`** and **`:9000`** as
the ground truth.

---

## 2. HAL for fleet teleop (`krabby-locomotion.service`)

Same model as field robots ([`FIELD-TELEOP.md`](FIELD-TELEOP.md)): locomotion stays up
via systemd after enroll.

Ensure **`/etc/krabby/locomotion.json`** exists (written at enroll). Pull the image if
needed: `krabby update` or `docker pull public.ecr.aws/t7t7b3i3/krabby-locomotion:release-latest`.

ZED cache (see [`docs/JETSON_DEPLOYMENT.md`](../docs/JETSON_DEPLOYMENT.md)):

```bash
mkdir -p ~/zed-resources/resources ~/zed-resources/settings
```

**Bench E2E** needs **`--teleop-control-echo`** in the HAL process
([`test_teleop_e2e.py`](service/tests_e2e/test_teleop_e2e.py)). Persist it via
**`/etc/krabby/locomotion.json`** (read by **`krabby run`** / **`krabby-locomotion.service`**):

```bash
sudo jq '.teleop_control_echo = true' /etc/krabby/locomotion.json | sudo tee /etc/krabby/locomotion.json.tmp \
  && sudo mv /etc/krabby/locomotion.json.tmp /etc/krabby/locomotion.json
sudo systemctl restart krabby-locomotion
```

New enroll on a bench CI kit: **`krabby enroll --locomotion-teleop-control-echo`**. One-off
without editing JSON: **`krabby run -- --teleop-control-echo`**.

```bash
sudo systemctl enable --now krabby-locomotion
docker logs -f krabby    # container name krabby
```

**Success in HAL logs:** `Teleop outbound signaling started` → **`ws://127.0.0.1:9000/ws/robot`**

---

## 3. Common misconfigurations

| Problem | Symptom |
|---------|---------|
| **`krabby run --gamepad-only`** on the bench | No `--teleop-ip`; fleet teleop broken |
| **Locomotion stopped** | Signaling at agent; no WebRTC **Playing** |
| **Agent down / wrong venv in unit** | No listener on **:9000** |
| **LAN `TELEOP_IP` in old launch scripts** | HAL not dialing agent shim |

---

## 4. Shadow telemetry red flags (portal HAL)

`krabby get telemetry` (via agent) may still show:

- **`hal_no_observation`** — the probe uses **`tcp://127.0.0.1:6001`**, but portal
  HAL uses **inproc** ZMQ. **Expected in portal mode**; teleop can still work.
- **`mcu_missing`** — OK for signaling/video E2E; joint motion needs MCU/firmware.

---

## 5. End-to-end check (operator machine)

With **`krabby-agent`** and **`krabby-locomotion`** active on the bench:

```bash
cd fleet/service && source .venv/bin/activate
export BENCH_E2E=1 COGNITO_CI_PASSWORD='…'   # + AWS creds for MQTT sniffer
pytest tests_e2e/test_teleop_e2e.py::test_teleop_signaling_control_and_video -q
```

Full suite: [`service/tests_e2e/README.md`](service/tests_e2e/README.md).

Manual smoke: portal **Open teleop** or `krabby-fleet teleop bench-krabby-ci`.
