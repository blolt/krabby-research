import enum
import math
from dataclasses import dataclass
from typing import Optional, Union


class PackVoltageRegion(enum.IntEnum):
    """Which voltage band pack_v falls in. A measurement, not a decision."""

    NORMAL = 0
    WARN = 1
    SOFT_CUT = 2
    HARD_CUT = 3
    OVER_VOLT = 4


def _known_or_raw(enum_type, value):
    """Keep a defined value as its enum member, an undefined one as a plain int."""
    try:
        return enum_type(value)
    except ValueError:
        return value


def _label(value) -> str:
    return value.name if isinstance(value, enum.IntEnum) else str(value)


@dataclass
class BatteryTelemetry:
    pack_volts: float
    pack_current_amperes: float
    pack_power_watts: float
    pack_charge_coulombs: float
    battery_a_volts: float
    battery_b_volts: float
    divergence: bool
    # Unknown bytes are retained as plain ints rather than coerced or dropped, so
    # a firmware that gains a value stays parseable and the unknown stays visible.
    pack_region: Union[PackVoltageRegion, int]
    # Per-monitor liveness, the same convention as the IMU segment's valid byte.
    # When false, that monitor's fields carry its last trustworthy reading.
    pack_valid: bool
    midpoint_valid: bool

    TAG = "BATT"
    TOKEN_COUNT = 11

    @classmethod
    def from_tokens(cls, tokens) -> Optional["BatteryTelemetry"]:
        if not tokens or tokens[0] != cls.TAG:
            return None
        if len(tokens) != cls.TOKEN_COUNT:
            return None
        try:
            values = tuple(float(token) for token in tokens[1:7])
        except ValueError:
            return None
        # Each boolean byte is checked on its own: a bad validity byte for one
        # monitor must not discard the other monitor's reading.
        if any(tokens[i] not in ("0", "1") for i in (7, 9, 10)):
            return None
        try:
            region_value = int(tokens[8])
        except ValueError:
            return None
        if not 0 <= region_value <= 255:
            return None
        if not all(math.isfinite(value) for value in values):
            return None
        return cls(
            *values,
            tokens[7] == "1",
            _known_or_raw(PackVoltageRegion, region_value),
            tokens[9] == "1",
            tokens[10] == "1",
        )

    @classmethod
    def from_segment(cls, segment: str) -> Optional["BatteryTelemetry"]:
        return cls.from_tokens(segment.split())

    def format_compact(self) -> str:
        region = _label(self.pack_region)
        divergence = " DIVERGE" if self.divergence else ""
        down = "".join(
            f" {name}:DOWN"
            for name, ok in (("pack", self.pack_valid), ("mid", self.midpoint_valid))
            if not ok
        )
        return (
            f"pack:{self.pack_volts:.2f}V "
            f"{self.pack_current_amperes:+.2f}A "
            f"{self.pack_power_watts:.1f}W "
            f"A:{self.battery_a_volts:.2f}V "
            f"B:{self.battery_b_volts:.2f}V "
            f"q:{self.pack_charge_coulombs:.0f}C {region}{divergence}{down}"
        )
