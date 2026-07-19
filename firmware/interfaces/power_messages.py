"""Power-state control messages between the leader MCU and the Orin (M16 Task 4).

The battery state machine on the leader Mega and the Orin-side power daemon
exchange these over the *same* serial link as joint telemetry, each on its own
``PWR``-prefixed line so they never collide with a telemetry line. Directions:

    Mega -> Orin : POWERING_DOWN, RESUMING, OVER_VOLTAGE_SHUTDOWN
    Orin -> Mega : SHUTDOWN_ACK

Wire format (whitespace-separated, matching the rest of the serial protocol)::

    PWR <schema_version> <TYPE> [reason]

``schema_version`` leads so a reader can reject or adapt to an unknown layout
*before* interpreting the rest -- a message whose schema this parser does not
know is dropped rather than guessed at, the same discipline the telemetry parser
uses for unknown segment tags.
"""
import enum
from dataclasses import dataclass
from typing import Optional

# Line prefix that marks a power-control message (vs. a telemetry or VER line).
POWER_MSG_PREFIX = "PWR"

# Bump when the field layout changes. A reader that sees a schema it does not
# recognize drops the message instead of misparsing it.
POWER_MSG_SCHEMA = 1


class PowerMessageType(enum.Enum):
    POWERING_DOWN = "POWERING_DOWN"                # Mega -> Orin: shut down cleanly
    SHUTDOWN_ACK = "SHUTDOWN_ACK"                  # Orin -> Mega: ack, poweroff underway
    RESUMING = "RESUMING"                          # Mega -> Orin: pack recovered, powering back on
    OVER_VOLTAGE_SHUTDOWN = "OVER_VOLTAGE_SHUTDOWN" # Mega -> Orin: one-way protective cutout


class PowerReason(enum.Enum):
    UNDER_VOLTAGE_SOFT = "under_voltage_soft"  # SOFT_CUT graceful shutdown
    OVER_VOLTAGE = "over_voltage"              # charger/BMS fault
    MANUAL = "manual"                          # operator-commanded
    VOLTAGE_RECOVERED = "voltage_recovered"    # pack rose above RECOVERY


@dataclass
class PowerMessage:
    type: PowerMessageType
    reason: Optional[PowerReason] = None
    schema_version: int = POWER_MSG_SCHEMA

    def format_line(self) -> str:
        """Render the wire line (no trailing newline)."""
        parts = [POWER_MSG_PREFIX, str(self.schema_version), self.type.value]
        if self.reason is not None:
            parts.append(self.reason.value)
        return " ".join(parts)

    @classmethod
    def parse(cls, line: str) -> Optional["PowerMessage"]:
        """Parse one ``PWR`` line. Returns None if it is not a power message,
        the schema is unknown, or the type is unrecognized.

        An *unknown reason* on a known type is tolerated (the typed message is
        still actionable) -- reason codes may grow without a schema bump. An
        unknown *schema* or *type* is not guessed at.
        """
        tokens = line.split()
        if len(tokens) < 3 or tokens[0] != POWER_MSG_PREFIX:
            return None
        try:
            schema = int(tokens[1])
        except ValueError:
            return None
        if schema != POWER_MSG_SCHEMA:
            return None  # unknown layout; do not guess at the fields
        try:
            mtype = PowerMessageType(tokens[2])
        except ValueError:
            return None
        reason: Optional[PowerReason] = None
        if len(tokens) >= 4:
            try:
                reason = PowerReason(tokens[3])
            except ValueError:
                reason = None  # forward-compatible: keep the typed message
        return cls(type=mtype, reason=reason, schema_version=schema)
