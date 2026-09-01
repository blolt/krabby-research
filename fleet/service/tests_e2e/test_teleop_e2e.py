"""Teleop E2E: Playwright against real fleet portal + bench robot.

Requires a deployed fleet host, Cognito, and Bruce's bench Orin running
``krabby agent`` + the existing WebRTC edge agent (``--teleop-ip 127.0.0.1``).
Skipped unless ``BENCH_E2E=1`` and ``fleet/config/fleet.toml`` is complete
(Cognito IDs + URLs). See ``fleet/config/README.md``.

The bench's HAL server also needs ``--teleop-control-echo`` on its launch
command for the (b) HAL-ack assertion below -- this echo is off by default
everywhere else (a per-run flag, not a checked-in ``robot_settings.py``
constant), since no operator-facing feature reads it (see
``teleop/edge/robot_settings.py:build_teleop_edge_settings``).

Coverage:
  (a) Cognito auth → open teleop URL → signaling handshake (hello_ack / Playing)
  (b) ``krabby-control-v1`` opens; motion-safe control sent and its receipt
      confirmed via the ``last_control`` echo on the telemetry channel (real
      HAL ack, not just a client-side send() that didn't throw)
  (c) ≥1 video track from the bench camera
  (d) unauthenticated signaling WS rejected; no MQTT publish on ``…/signaling/in``
  teardown: browser closed; MQTT ``…/signaling/*`` quiet
"""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Any
from urllib.parse import quote, urlparse

import pytest
import requests

from tests_e2e._fleet_env import (
    AWS_REGION,
    BENCH_THING_NAME,
    COGNITO_APP_CLIENT_ID,
    COGNITO_USER_POOL_ID,
    FLEET_E2E_CONFIGURED,
    FLEET_PORTAL_URL,
    FLEET_SERVICE_URL,
)

BENCH_E2E = os.environ.get("BENCH_E2E", "") == "1"
SIGNALING_TIMEOUT_S = float(os.environ.get("TELEOP_E2E_SIGNALING_TIMEOUT_S", "90"))
VIDEO_TIMEOUT_S = float(os.environ.get("TELEOP_E2E_VIDEO_TIMEOUT_S", "120"))
CONTROL_TIMEOUT_S = float(os.environ.get("TELEOP_E2E_CONTROL_TIMEOUT_S", "60"))
MQTT_IDLE_SECS = float(os.environ.get("TELEOP_E2E_MQTT_IDLE_SECS", "8"))

pytestmark = pytest.mark.skipif(
    not (
        BENCH_E2E
        and FLEET_E2E_CONFIGURED
        and FLEET_PORTAL_URL
    ),
    reason="BENCH_E2E=1 and complete fleet/config/fleet.toml required",
)


def _viewer_url(thing: str, token: str) -> str:
    return (
        f"{FLEET_PORTAL_URL}/teleop/viewer.html"
        f"?thing={quote(thing)}&token={quote(token)}"
    )


def _signaling_ws_url(thing: str, token: str | None = None) -> str:
    parsed = urlparse(FLEET_SERVICE_URL)
    # FLEET_SERVICE_URL is https://host/api — WS goes through Caddy /api → service.
    host = parsed.netloc or parsed.path
    scheme = "wss" if (parsed.scheme or "https") == "https" else "ws"
    path = f"/api/devices/{quote(thing)}/teleop/signaling"
    qs = f"?token={quote(token)}" if token else ""
    return f"{scheme}://{host}{path}{qs}"


class _MqttSniffer:
    """Subscribe to teleop signaling topics; record inbound frames (SigV4 MQTT)."""

    def __init__(self, thing: str) -> None:
        self.thing = thing
        self.in_topic = f"teleop/{thing}/signaling/in"
        self.out_topic = f"teleop/{thing}/signaling/out"
        self.received_in: list[tuple[float, str]] = []
        self.received_out: list[tuple[float, str]] = []
        self._lock = threading.Lock()
        self._connection: Any = None

    def start(self) -> None:
        from awscrt import auth, mqtt
        from awsiot import mqtt_connection_builder

        iot = __import__("boto3").client("iot", region_name=AWS_REGION)
        endpoint = iot.describe_endpoint(endpointType="iot:Data-ATS")["endpointAddress"]
        credentials_provider = auth.AwsCredentialsProvider.new_default_chain()
        client_id = f"teleop-e2e-sniffer-{os.getpid()}-{int(time.time())}"

        def _on_in(topic: str, payload: bytes, **kwargs: Any) -> None:
            text = payload.decode("utf-8", errors="replace")
            with self._lock:
                self.received_in.append((time.monotonic(), text))

        def _on_out(topic: str, payload: bytes, **kwargs: Any) -> None:
            text = payload.decode("utf-8", errors="replace")
            with self._lock:
                self.received_out.append((time.monotonic(), text))

        conn = mqtt_connection_builder.websockets_with_default_aws_signing(
            endpoint=endpoint,
            region=AWS_REGION,
            credentials_provider=credentials_provider,
            client_id=client_id,
            clean_session=True,
            keep_alive_secs=30,
        )
        conn.connect().result(timeout=30)
        conn.subscribe(topic=self.in_topic, qos=mqtt.QoS.AT_LEAST_ONCE, callback=_on_in)
        conn.subscribe(topic=self.out_topic, qos=mqtt.QoS.AT_LEAST_ONCE, callback=_on_out)
        self._connection = conn

    def stop(self) -> None:
        conn = self._connection
        self._connection = None
        if conn is None:
            return
        try:
            conn.disconnect().result(timeout=10)
        except Exception:
            pass

    def clear(self) -> None:
        with self._lock:
            self.received_in.clear()
            self.received_out.clear()

    def count_since(self, t0: float) -> tuple[int, int]:
        with self._lock:
            nin = sum(1 for t, _ in self.received_in if t >= t0)
            nout = sum(1 for t, _ in self.received_out if t >= t0)
            return nin, nout

    def out_has_type(self, msg_type: str) -> bool:
        with self._lock:
            for _, text in self.received_out:
                try:
                    if json.loads(text).get("type") == msg_type:
                        return True
                except json.JSONDecodeError:
                    continue
        return False


@pytest.fixture
def mqtt_sniffer() -> Any:
    sniffer = _MqttSniffer(BENCH_THING_NAME)
    sniffer.start()
    try:
        yield sniffer
    finally:
        sniffer.stop()


def test_teleop_signaling_control_and_video(operator_token: str, mqtt_sniffer: _MqttSniffer):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    mqtt_sniffer.clear()
    url = _viewer_url(BENCH_THING_NAME, operator_token)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)

        # (a) Signaling handshake: viewer status → Playing (hello_ack + answer).
        page.wait_for_function(
            """() => {
              const t = window.__krabbyTeleop && window.__krabbyTeleop.getStatus
                ? window.__krabbyTeleop.getStatus() : '';
              return /playing/i.test(t);
            }""",
            timeout=int(SIGNALING_TIMEOUT_S * 1000),
        )
        deadline = time.monotonic() + SIGNALING_TIMEOUT_S
        while time.monotonic() < deadline:
            if mqtt_sniffer.out_has_type("hello_ack") or mqtt_sniffer.out_has_type("answer"):
                break
            time.sleep(0.5)
        else:
            # Browser may complete before sniffer catches frames; still require MQTT activity.
            nin, nout = mqtt_sniffer.count_since(0)
            assert nin + nout > 0, "expected MQTT traffic on teleop/{thing}/signaling/*"

        # (b) Control data channel + motion-safe InputController payload.
        page.wait_for_function(
            """() => {
              const dc = window.__krabbyTeleop && window.__krabbyTeleop.getControlDc
                ? window.__krabbyTeleop.getControlDc() : null;
              return dc && dc.readyState === 'open';
            }""",
            timeout=int(CONTROL_TIMEOUT_S * 1000),
        )
        sent = page.evaluate("() => window.__krabbyTeleop.sendMotionSafeControl()")
        assert sent is True

        # HAL ack: poll the existing telemetry channel's last_control echo
        # (added by hal/server/teleop_portal_signaling.py's merge_last_control_state)
        # rather than a new protocol message -- RS=true is only reachable if
        # the bench's real WebRTCInputController actually received and
        # applied this exact payload, not just a default/idle readback.
        page.wait_for_function(
            """() => {
              const t = window.__krabbyTeleop && window.__krabbyTeleop.getLastTelemetry
                ? window.__krabbyTeleop.getLastTelemetry() : null;
              return !!(t && t.last_control && t.last_control.RS === true);
            }""",
            timeout=int(CONTROL_TIMEOUT_S * 1000),
        )

        # (c) At least one camera <video> track attached.
        page.wait_for_function(
            """() => window.__krabbyTeleop.videoTrackCount() >= 1""",
            timeout=int(VIDEO_TIMEOUT_S * 1000),
        )

        browser.close()

    # Teardown: signaling topics idle after session ends.
    time.sleep(2.0)
    mqtt_sniffer.clear()
    t0 = time.monotonic()
    time.sleep(MQTT_IDLE_SECS)
    nin, nout = mqtt_sniffer.count_since(t0)
    assert nin == 0 and nout == 0, (
        f"expected teleop signaling idle after teardown; got in={nin} out={nout}"
    )


def test_teleop_unauthenticated_signaling_rejected(mqtt_sniffer: _MqttSniffer):
    """(d) No Cognito token → WS rejected; no MQTT frames on signaling/in."""
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    mqtt_sniffer.clear()
    ws_url = _signaling_ws_url(BENCH_THING_NAME, token=None)
    t0 = time.monotonic()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        result = page.evaluate(
            """async (url) => {
              return await new Promise((resolve) => {
                let opened = false;
                const ws = new WebSocket(url);
                const timer = setTimeout(() => {
                  try { ws.close(); } catch (e) {}
                  resolve({ opened, closed: true, timedOut: true });
                }, 8000);
                ws.onopen = () => { opened = true; };
                ws.onerror = () => {};
                ws.onclose = (ev) => {
                  clearTimeout(timer);
                  resolve({ opened, closed: true, code: ev.code, timedOut: false });
                };
              });
            }""",
            ws_url,
        )
        browser.close()

    assert not result.get("opened"), f"unauthenticated WS must not open: {result}"
    time.sleep(1.0)
    nin, _ = mqtt_sniffer.count_since(t0)
    assert nin == 0, f"unauthenticated session must not publish signaling/in (got {nin} frames)"


def test_teleop_ice_servers_requires_auth():
    resp = requests.get(f"{FLEET_SERVICE_URL}/teleop/ice-servers", timeout=30)
    assert resp.status_code == 401


def test_teleop_ice_servers_authed(operator_token: str):
    resp = requests.get(
        f"{FLEET_SERVICE_URL}/teleop/ice-servers",
        headers={"Authorization": f"Bearer {operator_token}"},
        timeout=30,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("version") == 1
    assert isinstance(body.get("iceServers"), list) and body["iceServers"]
    urls = []
    for entry in body["iceServers"]:
        u = entry.get("urls")
        if isinstance(u, str):
            urls.append(u)
        elif isinstance(u, list):
            urls.extend(u)
    assert any(u.startswith("stun:") for u in urls)
