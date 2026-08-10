"""Control-plane E2E against the permanently enrolled bench Orin.

Enabled only when BENCH_E2E=1 is set. Without it, the whole module is skipped
so ordinary unit-test runs never touch AWS or the bench.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any, Iterator

import boto3
import pytest

BENCH_E2E = os.environ.get("BENCH_E2E", "").strip() in ("1", "true", "yes")
AWS_REGION = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
BENCH_THING_NAME = os.environ.get("BENCH_THING_NAME", "bench-krabby-ci")
SHADOW_MAX_AGE_SECS = int(os.environ.get("SHADOW_MAX_AGE_SECS", "180"))

KRAB_THING_TYPE = "Krab"
KRAB_DEVICE_POLICY = "KrabDevicePolicy"
AMAZON_ROOT_CA_URL = "https://www.amazontrust.com/repository/AmazonRootCA1.pem"
_LOCALPROXY_BIN = "localproxy"

pytestmark = pytest.mark.skipif(
    not BENCH_E2E,
    reason="BENCH_E2E not set (export BENCH_E2E=1 to run control-plane bench tests)",
)


def _iot() -> Any:
    return boto3.client("iot", region_name=AWS_REGION)


def _iot_data() -> Any:
    iot = _iot()
    endpoint = iot.describe_endpoint(endpointType="iot:Data-ATS")["endpointAddress"]
    return boto3.client("iot-data", endpoint_url=f"https://{endpoint}", region_name=AWS_REGION)


def _tunneling() -> Any:
    return boto3.client("iotsecuretunneling", region_name=AWS_REGION)


def _parse_indexed_shadow(shadow: Any) -> dict[str, Any]:
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


def _search_bench() -> dict[str, Any]:
    resp = _iot().search_index(
        queryString=f"thingName:{BENCH_THING_NAME} AND thingTypeName:{KRAB_THING_TYPE}",
        maxResults=1,
    )
    things = resp.get("things") or []
    assert things, f"SearchIndex returned no hit for {BENCH_THING_NAME}"
    return things[0]


def test_control_plane_prereqs():
    """Persistent ControlPlaneStack resources exist (reuse, don't redeploy)."""
    iot = _iot()
    iot.get_policy(policyName=KRAB_DEVICE_POLICY)
    iot.describe_thing_type(thingTypeName=KRAB_THING_TYPE)
    iot.describe_thing(thingName=BENCH_THING_NAME)


def test_bench_connectivity_and_shadow_index():
    """Connected + recent shadow reported.timestamp via Fleet Indexing."""
    thing = _search_bench()
    connectivity = thing.get("connectivity") or {}
    assert connectivity.get("connected") is True, (
        f"{BENCH_THING_NAME} is offline (connectivity={connectivity!r}) — bench offline = CI red"
    )
    assert connectivity.get("timestamp"), "missing connectivity.timestamp"

    reported = _parse_indexed_shadow(thing.get("shadow"))
    assert "timestamp" in reported, f"indexed shadow missing reported.timestamp: {reported!r}"
    age = time.time() - int(reported["timestamp"])
    assert age < SHADOW_MAX_AGE_SECS, (
        f"shadow reported.timestamp is {age:.0f}s old (limit {SHADOW_MAX_AGE_SECS}s) — "
        "is krabby-agent running on the bench?"
    )


def test_bench_get_thing_shadow_schema():
    """GetThingShadow returns expected open-ended reported fields."""
    resp = _iot_data().get_thing_shadow(thingName=BENCH_THING_NAME)
    payload = json.loads(resp["payload"].read())
    reported = payload.get("state", {}).get("reported")
    assert isinstance(reported, dict), f"expected state.reported object, got {reported!r}"
    assert isinstance(reported.get("timestamp"), int), reported
    # Agent may publish reported_image=null when no image is installed; AWS IoT
    # Device Shadow treats null as delete, so the key is often absent until
    # krabby install/update has written a ref.
    image = reported.get("reported_image")
    assert image is None or isinstance(image, str), image

    age = time.time() - int(reported["timestamp"])
    assert age < SHADOW_MAX_AGE_SECS, (
        f"GetThingShadow timestamp is {age:.0f}s old (limit {SHADOW_MAX_AGE_SECS}s)"
    )


@pytest.fixture
def scratch_device(tmp_path: Path) -> Iterator[dict[str, Any]]:
    """Provision a throwaway thing+cert with KrabDevicePolicy; tear down after."""
    iot = _iot()
    scratch_name = f"e2e-scratch-{os.urandom(4).hex()}"
    cert_path = tmp_path / "device.pem.crt"
    key_path = tmp_path / "private.pem.key"
    ca_path = tmp_path / "AmazonRootCA1.pem"

    iot.create_thing(thingName=scratch_name, thingTypeName=KRAB_THING_TYPE)
    created = iot.create_keys_and_certificate(setAsActive=True)
    cert_arn = created["certificateArn"]
    cert_id = created["certificateId"]
    cert_path.write_text(created["certificatePem"])
    key_path.write_text(created["keyPair"]["PrivateKey"])
    with urllib.request.urlopen(AMAZON_ROOT_CA_URL, timeout=15) as resp:
        ca_path.write_bytes(resp.read())

    iot.attach_policy(policyName=KRAB_DEVICE_POLICY, target=cert_arn)
    iot.attach_thing_principal(thingName=scratch_name, principal=cert_arn)

    endpoint = iot.describe_endpoint(endpointType="iot:Data-ATS")["endpointAddress"]
    info = {
        "thing_name": scratch_name,
        "cert_arn": cert_arn,
        "cert_id": cert_id,
        "cert_path": cert_path,
        "key_path": key_path,
        "ca_path": ca_path,
        "endpoint": endpoint,
    }
    try:
        yield info
    finally:
        try:
            iot.detach_policy(policyName=KRAB_DEVICE_POLICY, target=cert_arn)
        except Exception:  # noqa: BLE001 - best-effort teardown
            pass
        try:
            iot.detach_thing_principal(thingName=scratch_name, principal=cert_arn)
        except Exception:  # noqa: BLE001
            pass
        try:
            iot.update_certificate(certificateId=cert_id, newStatus="INACTIVE")
            iot.delete_certificate(certificateId=cert_id)
        except Exception:  # noqa: BLE001
            pass
        try:
            iot.delete_thing(thingName=scratch_name)
        except Exception:  # noqa: BLE001
            pass


def test_scratch_cert_cannot_update_bench_shadow(scratch_device: dict[str, Any]):
    """Per-thing isolation — scratch cert cannot write the bench shadow."""
    from awscrt import mqtt
    from awsiot import iotshadow, mqtt_connection_builder

    probe_key = f"e2e_isolation_{os.urandom(3).hex()}"
    before = json.loads(_iot_data().get_thing_shadow(thingName=BENCH_THING_NAME)["payload"].read())
    before_reported = (before.get("state") or {}).get("reported") or {}

    connection = mqtt_connection_builder.mtls_from_path(
        endpoint=scratch_device["endpoint"],
        cert_filepath=str(scratch_device["cert_path"]),
        pri_key_filepath=str(scratch_device["key_path"]),
        ca_filepath=str(scratch_device["ca_path"]),
        client_id=scratch_device["thing_name"],
        clean_session=True,
        keep_alive_secs=30,
    )
    connection.connect().result(timeout=20)
    shadow_client = iotshadow.IotShadowClient(connection)

    rejected: list[Any] = []
    accepted: list[Any] = []

    # Subscriptions on the *bench* topics should also be denied; we still try
    # the publish and verify the bench shadow never gains our probe key.
    try:
        shadow_client.subscribe_to_update_shadow_rejected(
            request=iotshadow.UpdateShadowSubscriptionRequest(thing_name=BENCH_THING_NAME),
            qos=mqtt.QoS.AT_LEAST_ONCE,
            callback=lambda err: rejected.append(err),
        )
    except Exception:  # noqa: BLE001 - deny is success for isolation
        pass
    try:
        shadow_client.subscribe_to_update_shadow_accepted(
            request=iotshadow.UpdateShadowSubscriptionRequest(thing_name=BENCH_THING_NAME),
            qos=mqtt.QoS.AT_LEAST_ONCE,
            callback=lambda resp: accepted.append(resp),
        )
    except Exception:  # noqa: BLE001
        pass

    request = iotshadow.UpdateShadowRequest(
        thing_name=BENCH_THING_NAME,
        state=iotshadow.ShadowState(reported={probe_key: True, "timestamp": int(time.time())}),
    )
    publish_error: Exception | None = None
    try:
        shadow_client.publish_update_shadow(request, mqtt.QoS.AT_LEAST_ONCE).result(timeout=15)
    except Exception as exc:  # noqa: BLE001 - unauthorized publish is expected
        publish_error = exc

    # Give any illicit accepted delivery a moment, then disconnect.
    time.sleep(2)
    connection.disconnect().result(timeout=15)

    after = json.loads(_iot_data().get_thing_shadow(thingName=BENCH_THING_NAME)["payload"].read())
    after_reported = (after.get("state") or {}).get("reported") or {}
    assert probe_key not in after_reported, (
        f"scratch cert wrote {probe_key} into bench shadow — isolation broken "
        f"(publish_error={publish_error!r}, rejected={rejected!r})"
    )
    assert not accepted, f"unexpected update/accepted for bench shadow: {accepted!r}"
    if "timestamp" in before_reported:
        assert "timestamp" in after_reported


@pytest.mark.skipif(not shutil.which(_LOCALPROXY_BIN), reason=f"{_LOCALPROXY_BIN} not on PATH")
def test_secure_tunnel_source_proxy_reaches_ssh():
    """OpenTunnel → destination localproxy on bench → source TCP sees SSH."""
    client = _tunneling()
    tunnel = client.open_tunnel(
        description=f"task1-e2e:{BENCH_THING_NAME}",
        destinationConfig={"thingName": BENCH_THING_NAME, "services": ["SSH"]},
        timeoutConfig={"maxLifetimeTimeoutMinutes": 30},
    )
    tunnel_id = tunnel["tunnelId"]
    source_token = tunnel["sourceAccessToken"]
    proc: subprocess.Popen | None = None
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            local_port = s.getsockname()[1]

        proc = subprocess.Popen(
            [_LOCALPROXY_BIN, "-s", str(local_port), "-t", source_token, "-r", AWS_REGION, "-c", "/etc/ssl/certs"],
        )
        deadline = time.monotonic() + 30
        banner = b""
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise AssertionError(f"localproxy exited early (code {proc.returncode})")
            try:
                with socket.create_connection(("127.0.0.1", local_port), timeout=1.0) as conn:
                    conn.settimeout(5.0)
                    # Destination proxy targets localhost:22 — SSH banner proves bytes flow.
                    banner = conn.recv(64)
                    if banner:
                        break
            except OSError:
                time.sleep(0.5)
        assert banner.startswith(b"SSH-"), (
            f"expected SSH banner through Secure Tunnel, got {banner!r} — "
            "is krabby-agent subscribed to tunnels/notify on the bench?"
        )
    finally:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        try:
            client.close_tunnel(tunnelId=tunnel_id, delete=True)
        except Exception:  # noqa: BLE001
            pass
