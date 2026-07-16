"""krabby-fleet devices: list enrolled robots and their connectivity."""
from __future__ import annotations

from krabby_fleet_cli._api import list_devices
from krabby_fleet_cli._auth import get_access_token
from krabby_fleet_cli._config import load_config


def cmd_devices() -> None:
    config = load_config()
    access_token = get_access_token(config)
    devices = list_devices(config, access_token)

    if not devices:
        print("No devices found.")
        return

    for device in devices:
        status = "connected" if device["connected"] else "disconnected"
        print(f"{device['thingName']}\t{status}")
