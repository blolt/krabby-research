"""Orin power daemon (M16 Task 4). Imports hal, so it runs in the Docker test
image; the SDK reader-loop dispatch is covered separately in
tests/unit/firmware/test_power_dispatch.py (no hal import, runs anywhere).

The daemon has no thread of its own; it hangs a callback on the SDK's serial
reader. These tests exercise the callback logic with a fake SDK (no real port).
"""
from firmware.interfaces.power_messages import (
    EmergencyShutdownReason,
    PowerMessage,
    PowerMessageType,
    PoweringDownReason,
    ResumingReason,
)
from hal.server.jetson.power_daemon import OrinPowerDaemon


class FakeSDK:
    """Minimal stand-in: the attributes/methods the daemon touches."""

    def __init__(self):
        self.on_power_message = None
        self.sent = []

    def send_power_message(self, msg):
        self.sent.append(msg)


class TestOrinPowerDaemon:
    def test_start_registers_the_callback_on_the_sdk(self):
        sdk = FakeSDK()
        daemon = OrinPowerDaemon(sdk)

        daemon.start()

        # A bound method compares unequal by identity across accesses; check the
        # registered callback belongs to this daemon instance.
        assert sdk.on_power_message is not None
        assert sdk.on_power_message.__self__ is daemon

    def test_stop_clears_only_its_own_callback(self):
        sdk = FakeSDK()
        daemon = OrinPowerDaemon(sdk)
        daemon.start()

        daemon.stop()

        assert sdk.on_power_message is None

    def test_stop_leaves_a_foreign_callback_untouched(self):
        # stop() must only clear ITS OWN callback: the `__self__ is self` identity
        # guard means a foreign handler installed by someone else survives stop().
        sdk = FakeSDK()
        daemon = OrinPowerDaemon(sdk)

        def foreign_cb(msg):
            pass

        sdk.on_power_message = foreign_cb
        daemon.stop()

        assert sdk.on_power_message is foreign_cb

    def test_powering_down_acks_then_powers_off(self):
        sdk = FakeSDK()
        calls = []
        daemon = OrinPowerDaemon(sdk, poweroff=lambda: calls.append("off"))

        daemon.handle(PowerMessage(
            PowerMessageType.POWERING_DOWN,
            PoweringDownReason.UNDER_VOLTAGE_SOFT,
        ))

        assert [m.type for m in sdk.sent] == [PowerMessageType.SHUTDOWN_ACK]
        assert calls == ["off"]

    def test_emergency_shutdown_is_not_acked_or_clean_poweroff_gated(self):
        sdk = FakeSDK()
        calls = []
        daemon = OrinPowerDaemon(sdk, poweroff=lambda: calls.append("off"))

        daemon.handle(PowerMessage(
            PowerMessageType.EMERGENCY_SHUTDOWN,
            EmergencyShutdownReason.OVER_VOLTAGE,
        ))

        assert sdk.sent == []
        assert calls == []

    def test_repeated_power_down_powers_off_once(self):
        # The leader repeats POWERING_DOWN every tick through its ack window.
        sdk = FakeSDK()
        calls = []
        daemon = OrinPowerDaemon(sdk, poweroff=lambda: calls.append("off"))

        for _ in range(5):
            daemon.handle(PowerMessage(
                PowerMessageType.POWERING_DOWN,
                PoweringDownReason.UNDER_VOLTAGE_SOFT,
            ))

        assert calls == ["off"]
        assert len(sdk.sent) == 1

    def test_resuming_and_ack_do_not_power_off(self):
        sdk = FakeSDK()
        calls = []
        daemon = OrinPowerDaemon(sdk, poweroff=lambda: calls.append("off"))

        daemon.handle(PowerMessage(
            PowerMessageType.RESUMING,
            ResumingReason.VOLTAGE_RECOVERED,
        ))
        daemon.handle(PowerMessage(PowerMessageType.SHUTDOWN_ACK))

        assert calls == []
        assert sdk.sent == []

    def test_resuming_rearms_for_a_later_power_down(self):
        # If the pack rebounds above RECOVERY before the MCU cuts the rail, this
        # process survives and RESUMING re-arms it: a later genuine POWERING_DOWN
        # must ack and power off AGAIN, not be swallowed by the first shutdown's
        # idempotency guard.
        sdk = FakeSDK()
        calls = []
        daemon = OrinPowerDaemon(sdk, poweroff=lambda: calls.append("off"))

        daemon.handle(PowerMessage(
            PowerMessageType.POWERING_DOWN,
            PoweringDownReason.UNDER_VOLTAGE_SOFT,
        ))
        assert calls == ["off"]
        assert [m.type for m in sdk.sent] == [PowerMessageType.SHUTDOWN_ACK]

        daemon.handle(PowerMessage(
            PowerMessageType.RESUMING,
            ResumingReason.VOLTAGE_RECOVERED,
        ))

        daemon.handle(PowerMessage(
            PowerMessageType.POWERING_DOWN,
            PoweringDownReason.UNDER_VOLTAGE_SOFT,
        ))
        assert calls == ["off", "off"]
        assert [m.type for m in sdk.sent] == [
            PowerMessageType.SHUTDOWN_ACK,
            PowerMessageType.SHUTDOWN_ACK,
        ]

    def test_poweroff_runs_even_if_ack_send_raises(self):
        # The pack is dying; a failed ack write must not prevent the poweroff.
        class RaisingSDK(FakeSDK):
            def send_power_message(self, msg):
                raise OSError("serial gone")

        sdk = RaisingSDK()
        calls = []
        daemon = OrinPowerDaemon(sdk, poweroff=lambda: calls.append("off"))

        try:
            daemon.handle(PowerMessage(
                PowerMessageType.POWERING_DOWN,
                PoweringDownReason.UNDER_VOLTAGE_SOFT,
            ))
        except OSError:
            pass  # the raise propagates after finally; poweroff must have run

        assert calls == ["off"]
