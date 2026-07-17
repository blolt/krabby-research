# krabby-fleet

Operator CLI for the Krabby fleet.

## Config

`~/.config/krabby-fleet/config.toml`:

```toml
[fleet]
service_url = "https://{fleet-domain}/api"

[cognito]
user_pool_id = "{cognito-user-pool-id}"
client_id = "{cognito-app-client-id}"

[ssh]
default_user = "operator"
```

`[ssh].default_user` is optional (defaults to `operator`).

## `krabby-fleet list`

```
krabby-fleet list
```

Hits `GET /devices` with a Cognito access token and prints one line per robot:
thing name, online/offline, last-seen (from Fleet Indexing connectivity), and a
short telemetry summary from the latest shadow `reported` document
(`reported_image`, shadow timestamp, container health, red flags).

`krabby-fleet devices` is an alias for the same command.

## `krabby-fleet ssh <robot>`

```
krabby-fleet ssh bench-krabby-ci
krabby-fleet ssh bench-krabby-ci --user someoneelse
```

1. Authenticates against Cognito via SRP (`USER_SRP_AUTH`, no browser) using
   `pycognito`. Tokens are cached at `~/.config/krabby-fleet/session.json`
   (mode `0600`) and refreshed automatically on the next run; if there's no
   valid cached session, prompts for a username and password.
2. `POST /devices/{robot}/ssh-tunnel` on the fleet service, with the Cognito
   access token as a bearer token. 401 means the session is invalid; 403
   means the account isn't in the `operator` group.
3. Picks a free local TCP port and spawns `localproxy` in source mode
   against it, using the returned `sourceAccessToken`.
4. Runs `ssh {user}@localhost -p {local-port}` once the proxy is listening.
   Host key checking is disabled for this connection -- each session gets a
   fresh port, so there's no stable `localhost:{port}` identity to check
   against `known_hosts`; the Secure Tunnel's own short-lived,
   Cognito-gated access token is the actual security boundary.
5. On exit (normal, Ctrl-C, or error), terminates the local proxy process
   and calls `DELETE /devices/{robot}/ssh-tunnel/{tunnelId}` to force-close
   the tunnel.

Requires `aws-iot-securetunneling-localproxy` (the `localproxy` binary) on
`PATH`, and an `ssh` client.

## Tests

```bash
cd fleet/cli
pip install -e ".[dev]"
pytest tests/
```

No real Cognito, AWS, or fleet-service access needed -- `test_auth.py`
patches the two functions that actually call `pycognito` and exercises only
the session-cache/refresh/login branching; `test_api.py` mocks `requests`;
`test_localproxy.py` mocks `subprocess.Popen`/`shutil.which` and uses a real
local socket to verify port readiness detection.
