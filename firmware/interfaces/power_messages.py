"""Power-state control messages between the leader MCU and the Orin (M16 Task 4).

The battery state machine on the leader Mega and the Orin-side power daemon
exchange these over the *same* serial link as joint telemetry, each on its own
``PWR``-prefixed line so they never collide with a telemetry line. Directions:

    Mega -> Orin : POWERING_DOWN, RESUMING, EMERGENCY_SHUTDOWN
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
from typing import Optional, Union

# Line prefix that marks a power-control message (vs. a telemetry or VER line).
POWER_MSG_PREFIX = "PWR"

# Bump when the field layout changes. A reader that sees a schema it does not
# recognize drops the message instead of misparsing it.
POWER_MSG_SCHEMA = 1


class PowerMessageType(enum.Enum):
    POWERING_DOWN = "POWERING_DOWN"          # graceful; ACK/timeout gates sleep
    SHUTDOWN_ACK = "SHUTDOWN_ACK"            # Orin -> Mega: clean poweroff underway
    RESUMING = "RESUMING"                    # pack recovered, powering back on
    EMERGENCY_SHUTDOWN = "EMERGENCY_SHUTDOWN"  # immediate; never ACK-gated


class PoweringDownReason(enum.Enum):
    UNDER_VOLTAGE_SOFT = "under_voltage_soft"
    MANUAL = "manual"


class EmergencyShutdownReason(enum.Enum):
    HARD_CUT = "hard_cut"
    OVER_VOLTAGE = "over_voltage"


class ResumingReason(enum.Enum):
    VOLTAGE_RECOVERED = "voltage_recovered"


PowerMessageReason = Union[
    PoweringDownReason,
    EmergencyShutdownReason,
    ResumingReason,
]


@dataclass
class PowerMessage:
    type: PowerMessageType
    reason: Optional[PowerMessageReason] = None
    schema_version: int = POWER_MSG_SCHEMA

    def __post_init__(self) -> None:
        # Producers may emit only the schema implemented by this class. The
        # decimal token is the ASCII wire encoding of this uint8-domain value;
        # parsers independently reject unknown future schemas before dispatch.
        if (
            type(self.schema_version) is not int
            or self.schema_version != POWER_MSG_SCHEMA
        ):
            raise ValueError(
                f"unsupported power-message schema: {self.schema_version!r}"
            )
        expected_reason_type = {
            PowerMessageType.POWERING_DOWN: PoweringDownReason,
            PowerMessageType.EMERGENCY_SHUTDOWN: EmergencyShutdownReason,
            PowerMessageType.RESUMING: ResumingReason,
        }.get(self.type)
        if expected_reason_type is None:
            if self.reason is not None:
                raise ValueError(f"{self.type.value} does not carry a reason")
        elif not isinstance(self.reason, expected_reason_type):
            raise ValueError(
                f"{self.type.value} requires {expected_reason_type.__name__}"
            )

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

        Message-specific reason enums enforce the graceful/emergency hierarchy.
        Missing, unknown, cross-family, or extra fields are rejected rather than
        converted into an actionable message with lost semantics.
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
        reason_type = {
            PowerMessageType.POWERING_DOWN: PoweringDownReason,
            PowerMessageType.EMERGENCY_SHUTDOWN: EmergencyShutdownReason,
            PowerMessageType.RESUMING: ResumingReason,
        }.get(mtype)
        expected_token_count = 3 if reason_type is None else 4
        if len(tokens) != expected_token_count:
            return None
        reason: Optional[PowerMessageReason] = None
        if reason_type is not None:
            try:
                reason = reason_type(tokens[3])
            except ValueError:
                return None
        return cls(type=mtype, reason=reason, schema_version=schema)
