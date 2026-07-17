# krabby-fleet-portal

Next.js operator portal for the Krabby fleet: Cognito sign-in, device list,
device detail (1/min shadow telemetry), and Open SSH.

## Routes

| Path | Purpose |
|------|---------|
| `/login` | Cognito Hosted UI sign-in |
| `/devices` | Device list (`thingName`, online/last-seen, `reported_image`) |
| `/devices/[thingName]` | Detail: health / IMU / pose / power / red flags + Open SSH |

Open SSH calls `POST /api/devices/{thing}/ssh-tunnel` (fleet service via Caddy,
or Next rewrite in local `next dev`). The button shows a `krabby-fleet ssh`
one-liner and a `localproxy` fallback with the short-lived source token.
AWS credentials never reach the browser.

## Auth

Auth.js (NextAuth v5) + Cognito authorization-code + PKCE against the
`FleetOperatorClient` from `FleetServiceStack` (public client, no secret).
Access tokens are stored in the JWT session and used as
`Authorization: Bearer` against the fleet service (operator group required).

## Configuration

Copy `.env.example` to `.env.local`:

| Variable | Purpose |
|----------|---------|
| `AUTH_SECRET` | Auth.js cookie signing secret |
| `AUTH_URL` | Public portal origin (`https://fleet…` or `http://localhost:3000`) |
| `AUTH_COGNITO_ID` | Cognito app client ID |
| `AUTH_COGNITO_ISSUER` | `https://cognito-idp.{region}.amazonaws.com/{userPoolId}` |
| `FLEET_SERVICE_URL` | Fleet REST base as seen by the Next server (`http://127.0.0.1:8080` on EC2) |

## Develop

Uses the Node toolchain under `fleet/infra/.tools/node` if system Node is
unavailable:

```bash
export PATH="$(pwd)/../infra/.tools/node/bin:$PATH"
cd fleet/portal
npm install
npm run dev
```

```bash
npm test
npm run build   # produces `.next/standalone` for EC2
```

## Production shape

`next build` with `output: "standalone"`. On every
`deploy-fleet-service.sh` run, SSM:

1. Unzips portal source to `/opt/krabby-fleet-portal-src`
2. Runs `npm ci && npm run build` and assembles `/opt/krabby-fleet-portal`
3. Writes `/etc/krabby-fleet/portal.env` (Cognito + `AUTH_SECRET` from Secrets Manager)
4. Installs `systemd/krabby-fleet-portal.service` and restarts it

Caddy (`fleet/service/deploy/Caddyfile`):

| Path | Backend |
|------|---------|
| `/api/auth*` | portal `:3000` (NextAuth) |
| `/api/*` | fleet service `:8080` (prefix stripped) |
| everything else | portal `:3000` |

```bash
journalctl -u krabby-fleet-portal -f
journalctl -u krabby-fleet-service -f
journalctl -u caddy -f
```
