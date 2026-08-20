from dataclasses import dataclass
import math
import re
from typing import Tuple, Optional

# Wire format: must match firmware (actuator_manager.h + arduino.ino).
# Line starts with a role prefix "FRONT; ", "UNKNOWN; ", "LEFT; ", or "RIGHT; " then semicolon-separated segments.
# Forwarded lines from left/right already include their role (LEFT; / RIGHT; ).
# Example: "FRONT; FLHY 0.123 0 512 1 0 0 128 0;FLHL ...;..."
# Segment format: <name> <pos> <pot> <current> <enL> <enR> <pwmL> <pwmR> <saf>
# saf: cumulative HallA edge count since boot (pins depend on KRABBY_PIN_REV in board_pins.h).


@dataclass
class JointTelemetry:
    name: str
    pos: float
    pot: int
    current: int
    en: Tuple[int, int]
    pwm: Tuple[int, int]
    saf: int
    # Appended tenth field. True when the sender omits it: an older board that
    # cannot report evidence is not itself evidence of the absence of any.
    attachment_verified: bool = True

    # Role prefix (first segment of a line); not a joint.
    ROLE_PREFIXES = ("JT", "FRONT", "UNKNOWN", "LEFT", "RIGHT")
    NAME_RE = re.compile(r"^[FRM][LR](?:HY|HL|KL)$")

    @classmethod
    def from_tokens(cls, tokens) -> Optional["JointTelemetry"]:
        if not tokens:
            return None
        if tokens[0] in cls.ROLE_PREFIXES:
            tokens = tokens[1:] if tokens[0] == "JT" else None
        if not tokens or len(tokens) not in (9, 10):
            return None
        name, pos, pot, cur, enL, enR, pwmL, pwmR, saf = tokens[:9]
        if not cls.NAME_RE.match(name):
            return None
        try:
            return cls(
                name=name,
                pos=float(pos),
                pot=int(pot),
                current=int(cur),
                en=(int(enL), int(enR)),
                pwm=(int(pwmL), int(pwmR)),
                saf=int(saf),
                attachment_verified=tokens[9] != "0" if len(tokens) == 10 else True,
            )
        except ValueError:
            return None

    @classmethod
    def parse_line(cls, line: str):
        from firmware.interfaces.telemetry_parser import parse_telemetry_line

        return parse_telemetry_line(line).joints

    @property
    def connected(self) -> bool:
        return math.isfinite(self.pos)

    def format_compact(self, target: Optional[float] = None) -> str:
        if not self.connected:
            return f"{self.name}:DISC,{self.pot},{self.current}"
        pos_part = f"{self.pos:.3f}"
        if target is not None:
            pos_part = f"{pos_part}/{target:.3f}"
        return (
            f"{self.name}:{pos_part},{self.pot},{self.current},"
            f"({self.en[0]},{self.en[1]}),({self.pwm[0]},{self.pwm[1]}),{self.saf}"
        )
