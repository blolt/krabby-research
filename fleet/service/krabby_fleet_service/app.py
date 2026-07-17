"""krabby-fleet-service -- Cognito-authenticated REST proxy over AWS IoT.

Bound to 127.0.0.1:8080 (see `__main__.py`); Caddy terminates TLS and
reverse-proxies `/api/*` here. Device list/detail via Fleet Indexing and
Classic Shadow; Secure Tunneling open/close for SSH.
"""
from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI
from pydantic import BaseModel

from krabby_fleet_service._auth import require_operator
from krabby_fleet_service._devices import get_device, list_devices
from krabby_fleet_service._tunnels import close_ssh_tunnel, open_ssh_tunnel

app = FastAPI(title="krabby-fleet-service")


class SshTunnelResponse(BaseModel):
    tunnelId: str
    sourceAccessToken: str
    region: str


class DeviceSummary(BaseModel):
    thingName: str
    connected: bool
    connectivityTimestamp: int | None = None
    reported: dict[str, Any] = {}


class DeviceDetail(BaseModel):
    thingName: str
    thingTypeName: str | None = None
    attributes: dict[str, str] = {}
    connected: bool
    connectivityTimestamp: int | None = None
    reported: dict[str, Any] = {}


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/devices", response_model=list[DeviceSummary])
def get_devices(_claims: dict[str, Any] = Depends(require_operator)) -> list[dict[str, Any]]:
    return list_devices()


@app.get("/devices/{thing_name}", response_model=DeviceDetail)
def get_device_detail(
    thing_name: str, _claims: dict[str, Any] = Depends(require_operator)
) -> dict[str, Any]:
    return get_device(thing_name)


@app.post("/devices/{thing_name}/ssh-tunnel", response_model=SshTunnelResponse)
def create_ssh_tunnel(
    thing_name: str, _claims: dict[str, Any] = Depends(require_operator)
) -> dict[str, Any]:
    return open_ssh_tunnel(thing_name)


@app.delete("/devices/{thing_name}/ssh-tunnel/{tunnel_id}", status_code=204)
def delete_ssh_tunnel(
    thing_name: str, tunnel_id: str, _claims: dict[str, Any] = Depends(require_operator)
) -> None:
    close_ssh_tunnel(tunnel_id)
