"""Orin-side power daemon (M16 Task 4).

Listens for the leader MCU's power-down signal on the *existing* serial reader
(via KrabbyMCUSDK.on_power_message -- no second port), acks it, and triggers a
clean host poweroff. Started by hal/server/jetson/main.py alongside the HAL
server + inference client and torn down in its finally block.

Container -> host poweroff (OPEN DECISION): this process runs inside the
locomotion container, where `systemctl poweroff` does not reach the host. The
real mechanism is *injected* as `poweroff` -- host-systemd/D-Bus passthrough, a
small host-side helper the container signals, or simply relying on the MCU's
supply cut after the ack (the leader force-cuts the Orin 60 s after a shutdown
command per Task 4 §4). The default here only logs, so a deployment that forgot
to wire a real mechanism fails safe: it still acks, and the MCU cut takes it
down. See the Task 4 notes; confirm the mechanism with the grantor.
"""
import logging
from typing import Callable, Optional

from firmware.interfaces.power_messages import PowerMessage, PowerMessageType

logger = logging.getLogger("KrabbyPowerDaemon")

# Signals that mean "the pack is failing, take the Orin down now".
_SHUTDOWN_TYPES = (
    PowerMessageType.POWERING_DOWN,
    PowerMessageType.OVER_VOLTAGE_SHUTDOWN,
)


def _default_poweroff() -> None:
    logger.error(
        "Power-down acked but no host-poweroff mechanism is configured; relying "
        "on the MCU supply cut. Wire a real poweroff into main.py (see module docstring)."
    )


class OrinPowerDaemon:
    """Acks a power-down from the leader and powers the host off.

    Holds no thread of its own -- it hangs a callback on the SDK's serial reader,
    which already runs on its own thread. `poweroff` is the injected host-poweroff
    action (see the module docstring); omit it and a safe logging no-op is used.
    """

    def __init__(self, sdk, poweroff: Optional[Callable[[], None]] = None):
        # `poweroff` runs on the SDK's shared serial reader thread (handle() is
        # invoked inline from it), so it MUST be non-blocking / fire-and-forget
        # (spawn the host shutdown, don't wait on it) or it stalls telemetry reads.
        self._sdk = sdk
        self._poweroff = poweroff or _default_poweroff
        self._handled = False

    def start(self) -> None:
        self._sdk.on_power_message = self.handle
        logger.info("Orin power daemon armed; listening for POWERING_DOWN")

    def stop(self) -> None:
        # A bound method is a fresh object on every attribute access, so
        # `is self.handle` never matches; identify our callback by its instance.
        cb = getattr(self._sdk, "on_power_message", None)
        if getattr(cb, "__self__", None) is self:
            self._sdk.on_power_message = None

    def handle(self, msg: PowerMessage) -> None:
        """Reader-thread callback. Acks then powers off on a shutdown signal.

        Idempotent: the leader emits POWERING_DOWN exactly once, edge-triggered on
        the SOFT_CUT transition, and relies on its 60 s force-off window to take the
        Orin down regardless of the ack. The idempotency guard here defends against
        a duplicate line (a re-sent or double-parsed edge), not a per-tick repeat, so
        only the first shutdown acts. RESUMING re-arms us: if the pack rebounded above
        RECOVERY before the MCU cut the rail (so this process survived), a later
        genuine POWERING_DOWN must ack again. Our own SHUTDOWN_ACK needs no action here.
        """
        if msg.type is PowerMessageType.RESUMING:
            self._handled = False       # re-arm for a future shutdown after recovery
            return
        if msg.type not in _SHUTDOWN_TYPES:
            return
        if self._handled:
            return
        self._handled = True
        reason = msg.reason.value if msg.reason is not None else "-"
        logger.warning("Power-down received (%s / %s); acking and powering off host",
                       msg.type.value, reason)
        try:
            self._sdk.send_power_message(PowerMessage(PowerMessageType.SHUTDOWN_ACK))
        finally:
            # Always power off even if the ack write failed -- the pack is dying;
            # the ack is a courtesy, the poweroff is the point.
            self._poweroff()
