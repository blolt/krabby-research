from contextlib import nullcontext
from types import SimpleNamespace

from firmware.bench_tests import checks


def _battery(pack_valid, midpoint_valid):
    return SimpleNamespace(
        pack_valid=pack_valid,
        midpoint_valid=midpoint_valid,
    )


def _run(monkeypatch, groups, answers):
    opened = object()
    monkeypatch.setattr(checks.mcu, "open_port", lambda _port: nullcontext(opened))
    monkeypatch.setattr(
        checks.mcu, "collect",
        lambda ser, _count: groups.pop(0) if ser is opened else [],
    )
    monkeypatch.setattr(checks.mcu, "battery_of", lambda sample: sample)
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    return checks.ina_reconnect("ignored")


def test_ina_reconnect_checks_each_monitor_and_the_oled(monkeypatch):
    groups = [
        [_battery(True, True)] * 40,
        [_battery(False, True)] * 80,
        [_battery(True, True)] * 120,
        [_battery(True, False)] * 80,
        [_battery(True, True)] * 120,
    ]

    result = _run(monkeypatch, groups, iter(["", "", "y", "", "", "y"]))

    assert result.ok is True
    assert result.values["pack_absent_matching"] == 80
    assert result.values["midpoint_absent_matching"] == 80


def test_ina_reconnect_fails_if_pack_does_not_recover(monkeypatch):
    groups = [
        [_battery(True, True)] * 40,
        [_battery(False, True)] * 80,
        [_battery(False, True)] * 120,
        [_battery(True, False)] * 80,
        [_battery(True, True)] * 120,
    ]

    result = _run(monkeypatch, groups, iter(["", "", "y", "", "", "y"]))

    assert result.ok is False
    assert result.values["pack_recovered_matching"] == 0


def test_ina_reconnect_requires_visual_recovery(monkeypatch):
    groups = [
        [_battery(True, True)] * 40,
        [_battery(False, True)] * 80,
        [_battery(True, True)] * 120,
        [_battery(True, False)] * 80,
        [_battery(True, True)] * 120,
    ]

    result = _run(monkeypatch, groups, iter(["", "", "n", "", "", "y"]))

    assert result.ok is False
    assert result.values["pack_oled_recovered"] is False
