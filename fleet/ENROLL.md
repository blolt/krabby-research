# Device enroll (Orin)

One-time onboarding of a Jetson Orin into AWS IoT Core: thing, device cert
(CSR on-device), policy attach, identity files, and `krabby-agent.service`.

Run on the **Orin**, not the SSH source. Private key never leaves the device.
AWS creds are enroll-time only (not persisted).

Placeholders: `<region>`, `<thing-name>`. Tip: `export AWS_PAGER=""`.

## Prerequisites

- `ControlPlaneStack` deployed ([`infra/control-plane.md`](infra/control-plane.md)).
- IAM access key for user `krabby-enroll` (created once after control-plane
  deploy; not your admin key):

  `aws iam create-access-key --user-name krabby-enroll --output json`

## Install `krabby` on the Orin

```bash
cd /path/to/krabby-research
python3 -m venv .venv-krabby && source .venv-krabby/bin/activate
pip install -U pip && pip install ./krabby
command -v krabby
krabby --help | grep -E 'enroll|agent'
```

(Or `pip install -U krabby-launcher` once a published build includes
enroll/agent.)

## Enroll

Export **`krabby-enroll`** keys in this shell only (close the shell when done).
`aws` CLI is optional; enroll uses `boto3`.

```bash
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_DEFAULT_REGION=<region>
python -c "import boto3; print(boto3.client('sts').get_caller_identity())"
```

Pass when ARN ends with `user/krabby-enroll`.

```bash
sudo -E env PATH="$PATH" krabby enroll --thing-name <thing-name>
```

`-E` keeps AWS env vars; `PATH="$PATH"` keeps the venv `krabby` visible to
sudo. Omit `--thing-name` to default to the wired NIC MAC (no hostname
fallback). Optional: `--endpoint <IotAtsEndpoint>` if ATS auto-resolve fails.

Expect: thing/cert/policy, identity under `/etc/krabby/iot/`, MQTT verify
`[ok]`, `krabby-agent.service` enabled. Apt may fail with
`Unable to locate package aws-iot-securetunneling-localproxy` — identity can
still be fine; install `localproxy` next if you need tunnels/SSH.

## Destination `localproxy` (if apt failed)

Needed for Secure Tunneling SSH. Docker is only a download tool:

```bash
sudo docker pull public.ecr.aws/aws-iot-securetunneling-localproxy/ubuntu-bin:arm64-latest
sudo docker create --name krabby-lp public.ecr.aws/aws-iot-securetunneling-localproxy/ubuntu-bin:arm64-latest
sudo docker cp krabby-lp:/root/bin/localproxy /usr/local/bin/localproxy
sudo docker rm krabby-lp && sudo chmod 755 /usr/local/bin/localproxy
command -v localproxy
```

## Start agent

```bash
sudo systemctl start krabby-agent
sudo systemctl status krabby-agent --no-pager
journalctl -u krabby-agent -n 50 --no-pager
krabby get telemetry
```

`krabby agent` uses one MQTT connection for shadow telemetry (1/min), tunnel
notify → destination `localproxy` → `localhost:22`, and teleop signaling
shim. Details: [`krabby/README.md`](../krabby/README.md).

## Next

SSH from one source: [`SSH-TUNNEL.md`](SSH-TUNNEL.md). Console / SearchIndex:
[`README.md`](README.md).

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Policy / thing type missing | Deploy `ControlPlaneStack` first |
| Wrong IAM user | Use `krabby-enroll` keys, not admin |
| `sudo: krabby: command not found` | `sudo -E env PATH="$PATH" ...` with venv active |
| Apt missing `localproxy` | Docker extract above |
| Agent not connected | `journalctl -u krabby-agent -f --no-pager` |
