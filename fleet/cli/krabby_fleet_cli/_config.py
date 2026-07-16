"""~/.config/krabby-fleet/config.toml loading."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib  # type: ignore[import]
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

CONFIG_PATH = Path.home() / ".config" / "krabby-fleet" / "config.toml"


@dataclass(frozen=True)
class Config:
    service_url: str
    cognito_user_pool_id: str
    cognito_client_id: str
    default_ssh_user: str = "operator"


def load_config(path: Path = CONFIG_PATH) -> Config:
    if not path.exists():
        print(
            f"error: {path} not found. Create it with:\n\n"
            "[fleet]\n"
            'service_url = "https://<fleet-domain>/api"\n\n'
            "[cognito]\n"
            'user_pool_id = "<user-pool-id>"\n'
            'client_id = "<app-client-id>"\n\n'
            "[ssh]\n"
            'default_user = "operator"\n',
            file=sys.stderr,
        )
        sys.exit(1)

    raw = tomllib.loads(path.read_text())
    try:
        fleet = raw["fleet"]
        cognito = raw["cognito"]
    except KeyError as exc:
        print(f"error: {path} missing required section {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        service_url = fleet["service_url"]
        user_pool_id = cognito["user_pool_id"]
        client_id = cognito["client_id"]
    except KeyError as exc:
        print(f"error: {path} missing required key {exc}", file=sys.stderr)
        sys.exit(1)

    return Config(
        service_url=service_url.rstrip("/"),
        cognito_user_pool_id=user_pool_id,
        cognito_client_id=client_id,
        default_ssh_user=raw.get("ssh", {}).get("default_user", "operator"),
    )
