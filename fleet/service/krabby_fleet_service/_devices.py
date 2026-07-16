"""Fleet listing -- a thin proxy over boto3's iot SearchIndex.

Reads Fleet Indexing's registry + connectivity data (enabled by
`ControlPlaneStack`'s `thingIndexingConfiguration` /
`updateEventConfigurations`), not the device's shadow directly.
"""
from __future__ import annotations

from typing import Any

from krabby_fleet_service._config import AWS_REGION

# Must match fleet/infra/control_plane_stack.py's KRAB_THING_TYPE -- keep
# the two in sync if either changes.
KRAB_THING_TYPE = "Krab"


def _client() -> Any:
    import boto3

    return boto3.client("iot", region_name=AWS_REGION)


def list_devices() -> list[dict[str, Any]]:
    response = _client().search_index(queryString=f"thingTypeName:{KRAB_THING_TYPE}")
    devices = []
    for thing in response.get("things", []):
        connectivity = thing.get("connectivity") or {}
        devices.append(
            {
                "thingName": thing["thingName"],
                "connected": connectivity.get("connected", False),
                "connectivityTimestamp": connectivity.get("timestamp"),
            }
        )
    return devices
