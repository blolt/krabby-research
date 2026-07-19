"""Persistent AWS IoT MQTT connection for the teleop signaling bridge.

One SigV4-over-WebSocket MQTT client (instance-role credentials) is shared by
all browser teleop sessions for the life of the process. Reconnect is handled
by the CRT client; callers just publish/subscribe.
"""
from __future__ import annotations

import logging
import socket
import threading
import uuid
from typing import Any, Callable

logger = logging.getLogger(__name__)

# awscrt.mqtt.QoS.AT_LEAST_ONCE — avoid importing awscrt at module load (tests).
_QOS_AT_LEAST_ONCE = 1

MqttMessageCallback = Callable[[str, bytes], None]


class FleetMqttClient:
    """Thin wrapper around awsiot MQTT connection (websockets + default AWS signing)."""

    def __init__(self) -> None:
        self._connection: Any = None
        self._lock = threading.Lock()
        # topic -> list of callbacks (fan-out for shared topic filters)
        self._subscribers: dict[str, list[MqttMessageCallback]] = {}

    @property
    def connected(self) -> bool:
        return self._connection is not None

    def connect(self, *, endpoint: str, region: str, client_id: str | None = None) -> None:
        """Connect once. Safe to call only from the service lifespan / startup."""
        if self._connection is not None:
            raise RuntimeError("FleetMqttClient already connected")

        from awscrt import auth, mqtt
        from awsiot import mqtt_connection_builder

        cid = client_id or f"krabby-fleet-signaling-{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
        credentials_provider = auth.AwsCredentialsProvider.new_default_chain()

        def _on_interrupted(connection: Any, error: Any, **kwargs: Any) -> None:
            logger.warning("fleet MQTT interrupted: %s — reconnecting", error)

        def _on_resumed(connection: Any, return_code: Any, session_present: Any, **kwargs: Any) -> None:
            logger.info(
                "fleet MQTT resumed (return_code=%s, session_present=%s)",
                return_code,
                session_present,
            )

        connection = mqtt_connection_builder.websockets_with_default_aws_signing(
            endpoint=endpoint,
            region=region,
            credentials_provider=credentials_provider,
            client_id=cid,
            clean_session=True,
            keep_alive_secs=30,
            on_connection_interrupted=_on_interrupted,
            on_connection_resumed=_on_resumed,
        )
        connection.connect().result(timeout=30)
        self._connection = connection
        logger.info("fleet MQTT connected as %s to %s", cid, endpoint)
        # silence unused import warning when type-checkers look at mqtt.QoS
        _ = mqtt.QoS.AT_LEAST_ONCE

    def disconnect(self) -> None:
        conn = self._connection
        self._connection = None
        if conn is None:
            return
        try:
            conn.disconnect().result(timeout=10)
        except Exception as exc:
            logger.warning("fleet MQTT disconnect error: %s", exc)

    def publish(self, topic: str, payload: str | bytes) -> None:
        conn = self._connection
        if conn is None:
            raise RuntimeError("fleet MQTT not connected")
        data = payload if isinstance(payload, (bytes, bytearray)) else payload.encode("utf-8")
        conn.publish(topic=topic, payload=data, qos=_QOS_AT_LEAST_ONCE)

    def subscribe(self, topic: str, callback: MqttMessageCallback) -> None:
        """Subscribe ``topic`` (or topic filter) and register ``callback``.

        Multiple callbacks may share one MQTT subscription; the first
        registration issues the IoT subscribe.
        """
        conn = self._connection
        if conn is None:
            raise RuntimeError("fleet MQTT not connected")

        with self._lock:
            existing = self._subscribers.get(topic)
            if existing is not None:
                existing.append(callback)
                return
            self._subscribers[topic] = [callback]

        # Closed over for fan-out; callbacks are keyed by the filter we
        # subscribed with, not the concrete matched topic name.
        filter_topic = topic

        # awscrt detects "old" callbacks by binding topic=/payload=; the first
        # parameter must be named ``topic`` (not ``topic_name``) or subscribe
        # raises TypeError at registration time.
        def _on_message(topic: str, payload: bytes, **kwargs: Any) -> None:
            with self._lock:
                cbs = list(self._subscribers.get(filter_topic, ()))
            for cb in cbs:
                try:
                    cb(topic, payload)
                except Exception:
                    logger.exception("fleet MQTT subscriber callback failed topic=%s", topic)

        conn.subscribe(topic=filter_topic, qos=_QOS_AT_LEAST_ONCE, callback=_on_message)

    def unsubscribe(self, topic: str, callback: MqttMessageCallback) -> None:
        with self._lock:
            cbs = self._subscribers.get(topic)
            if not cbs:
                return
            try:
                cbs.remove(callback)
            except ValueError:
                return
            if cbs:
                return
            del self._subscribers[topic]

        conn = self._connection
        if conn is None:
            return
        try:
            conn.unsubscribe(topic)
        except Exception as exc:
            logger.warning("fleet MQTT unsubscribe %s failed: %s", topic, exc)
