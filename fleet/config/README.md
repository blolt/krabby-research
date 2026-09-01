# Fleet config

Single committed source for **non-secret** Krabby fleet settings: URLs, AWS
region, Cognito pool/client IDs, IoT thing type/policy names, bench thing name,
CI operator username.

**Secrets stay out of git:** only `COGNITO_CI_PASSWORD` in GitHub Actions
secrets (and local export for manual CI-style runs).

## File

[`fleet.toml`](fleet.toml) — edit after deploy to fill `[cognito]` from
`FleetServiceStack` outputs:

```bash
aws cloudformation describe-stacks --stack-name FleetServiceStack \
  --query "Stacks[0].Outputs[?OutputKey=='FleetCognitoUserPoolId' || OutputKey=='FleetCognitoUserPoolClientId'].[OutputKey,OutputValue]" \
  --output table
```

Set `[ci].operator_username` to the CI operator’s Cognito email (sign-in alias).

## Python client

```bash
pip install -e fleet/config
```

```python
from krabby_fleet_config import load_fleet_config, ci_cognito_password

cfg = load_fleet_config()
print(cfg.service_url, cfg.cognito_issuer)

password = ci_cognito_password()  # env only
```

Search order: `KRABBY_FLEET_CONFIG` → repo `fleet/config/fleet.toml` →
bundled path when installed editable → `~/.config/krabby-fleet/config.toml`.

## Who uses it

| Consumer | How |
|----------|-----|
| GitHub Actions | Checkout repo; tests/CLI load `fleet.toml`. Secret: password only. |
| `krabby-fleet` CLI | `pip install -e fleet/config -e fleet/cli`; loads shared config |
| Bench E2E pytest | Same package; `load_fleet_config().as_env()` |
| EC2 fleet service | **Not** this file — runtime reads SSM (`/krabby/fleet/*`) via instance role |
| `krabby enroll` on Orin | Thing type / policy names must match `[iot]` (constants in `enroll.py` today) |

## Operator override

Laptops without a repo checkout can copy the same TOML shape to
`~/.config/krabby-fleet/config.toml` (last resort in the search order).
