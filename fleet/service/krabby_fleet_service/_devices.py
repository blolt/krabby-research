"""Fleet device listing and detail -- thin proxy over IoT Fleet Indexing + shadows.

`list_devices` uses a single paginated `iot:SearchIndex` query for all Krabs
(connectivity + indexed classic-shadow `reported` in one round trip).
`get_device` uses `iot:DescribeThing` + `iot:GetThingShadow` for the
authoritative detail view, with connectivity filled from SearchIndex when
available.
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException

from krabby_fleet_service._config import AWS_REGION

# Must match ControlPlaneStack / krabby enroll.
KRAB_THING_TYPE = "Krab"


def _iot_client() -> Any:
    import boto3

    return boto3.client("iot", region_name=AWS_REGION)


def _iot_data_client() -> Any:
    import boto3

    iot = _iot_client()
    endpoint = iot.describe_endpoint(endpointType="iot:Data-ATS")["endpointAddress"]
    return boto3.client("iot-data", endpoint_url=f"https://{endpoint}", region_name=AWS_REGION)


def _parse_shadow_reported(shadow: Any) -> dict[str, Any]:
    if shadow is None:
        return {}
    if isinstance(shadow, str):
        try:
            shadow = json.loads(shadow)
        except json.JSONDecodeError:
            return {}
    if not isinstance(shadow, dict):
        return {}
    reported = shadow.get("reported")
    return reported if isinstance(reported, dict) else {}


def _thing_summary(thing: dict[str, Any]) -> dict[str, Any]:
    connectivity = thing.get("connectivity") or {}
    return {
        "thingName": thing["thingName"],
        "connected": bool(connectivity.get("connected", False)),
        "connectivityTimestamp": connectivity.get("timestamp"),
        "reported": _parse_shadow_reported(thing.get("shadow")),
    }


def list_devices() -> list[dict[str, Any]]:
    client = _iot_client()
    devices: list[dict[str, Any]] = []
    paginator = client.get_paginator("search_index")
    for page in paginator.paginate(queryString=f"thingTypeName:{KRAB_THING_TYPE}"):
        for thing in page.get("things", []):
            thing_name = thing.get("thingName")
            if not thing_name:
                continue
            devices.append(_thing_summary(thing))
    devices.sort(key=lambda item: item["thingName"])
    return devices


def _search_thing(thing_name: str) -> dict[str, Any] | None:
    client = _iot_client()
    response = client.search_index(
        queryString=f"thingName:{thing_name} AND thingTypeName:{KRAB_THING_TYPE}",
        maxResults=1,
    )
    things = response.get("things", [])
    return things[0] if things else None


def _get_reported_shadow(thing_name: str) -> dict[str, Any]:
    client = _iot_data_client()
    try:
        response = client.get_thing_shadow(thingName=thing_name)
    except client.exceptions.ResourceNotFoundException:
        return {}
    payload = json.loads(response["payload"].read())
    reported = payload.get("state", {}).get("reported")
    return reported if isinstance(reported, dict) else {}


def get_device(thing_name: str) -> dict[str, Any]:
    client = _iot_client()
    try:
        description = client.describe_thing(thingName=thing_name)
    except client.exceptions.ResourceNotFoundException as exc:
        raise HTTPException(status_code=404, detail="thing not found") from exc

    thing_type = description.get("thingTypeName")
    if thing_type and thing_type != KRAB_THING_TYPE:
        raise HTTPException(status_code=404, detail="thing not found")

    indexed = _search_thing(thing_name)
    connectivity = (indexed or {}).get("connectivity") or {}

    return {
        "thingName": thing_name,
        "thingTypeName": thing_type,
        "attributes": description.get("attributes") or {},
        "connected": bool(connectivity.get("connected", False)),
        "connectivityTimestamp": connectivity.get("timestamp"),
        "reported": _get_reported_shadow(thing_name),
    }
