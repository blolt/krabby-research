import math
from dataclasses import dataclass
from typing import Optional, Tuple



@dataclass
class ImuTelemetry:
    accel: Tuple[float, float, float]
    gyro: Tuple[float, float, float]
    temp_c: float
    valid: bool

    TAG = "IMU"
    TOKEN_COUNT = 9
    VALID_BY_TOKEN = {"0": False, "1": True}
    ACCEL_LABEL = "a"
    ACCEL_UNIT = "m/s2"
    ACCEL_DECIMALS = 2
    GYRO_LABEL = "g"
    GYRO_UNIT = "rad/s"
    GYRO_DECIMALS = 3
    TEMP_UNIT = "C"
    TEMP_DECIMALS = 1
    STALE_SUFFIX = " STALE"

    @classmethod
    def from_tokens(cls, tokens) -> Optional["ImuTelemetry"]:
        if not tokens or tokens[0] != cls.TAG:
            return None
        if len(tokens) != cls.TOKEN_COUNT:
            return None

        try:
            accel = tuple(float(token) for token in tokens[1:4])
            gyro = tuple(float(token) for token in tokens[4:7])
            temp_c = float(tokens[7])
        except ValueError:
            return None

        valid_token = tokens[8]
        if valid_token not in cls.VALID_BY_TOKEN:
            return None
        if not all(math.isfinite(value) for value in accel + gyro):
            return None
        if not math.isfinite(temp_c):
            temp_c = float("nan")
        return cls(accel, gyro, temp_c, cls.VALID_BY_TOKEN[valid_token])

    @classmethod
    def from_segment(cls, segment: str) -> Optional["ImuTelemetry"]:
        return cls.from_tokens(segment.split())

    @property
    def accel_g(self) -> Tuple[float, float, float]:
        return tuple(value / 9.80665 for value in self.accel)

    @property
    def gyro_dps(self) -> Tuple[float, float, float]:
        return tuple(value * 180.0 / math.pi for value in self.gyro)

    @property
    def roll_deg(self) -> float:
        _, accel_y, accel_z = self.accel
        return math.degrees(math.atan2(accel_y, accel_z))

    @property
    def pitch_deg(self) -> float:
        accel_x, accel_y, accel_z = self.accel
        return math.degrees(math.atan2(-accel_x, math.hypot(accel_y, accel_z)))

    def format_compact(self) -> str:
        accel_x, accel_y, accel_z = self.accel
        gyro_x, gyro_y, gyro_z = self.gyro
        stale = "" if self.valid else self.STALE_SUFFIX
        return (
            f"{self.ACCEL_LABEL}:"
            f"({accel_x:.{self.ACCEL_DECIMALS}f},"
            f"{accel_y:.{self.ACCEL_DECIMALS}f},"
            f"{accel_z:.{self.ACCEL_DECIMALS}f}){self.ACCEL_UNIT} "
            f"{self.GYRO_LABEL}:"
            f"({gyro_x:.{self.GYRO_DECIMALS}f},"
            f"{gyro_y:.{self.GYRO_DECIMALS}f},"
            f"{gyro_z:.{self.GYRO_DECIMALS}f}){self.GYRO_UNIT} "
            f"{self.temp_c:.{self.TEMP_DECIMALS}f}{self.TEMP_UNIT}{stale}"
        )
