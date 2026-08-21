from dataclasses import dataclass, field
from typing import List, Optional

from firmware.interfaces.battery_telemetry import BatteryTelemetry
from firmware.interfaces.imu_telemetry import ImuTelemetry
from firmware.interfaces.joint_telemetry import JointTelemetry


@dataclass
class ParsedTelemetry:
    joints: List[JointTelemetry] = field(default_factory=list)
    imu: Optional[ImuTelemetry] = None
    battery: Optional[BatteryTelemetry] = None
