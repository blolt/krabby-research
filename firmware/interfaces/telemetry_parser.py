from firmware.interfaces.battery_telemetry import BatteryTelemetry
from firmware.interfaces.imu_telemetry import ImuTelemetry
from firmware.interfaces.joint_telemetry import JointTelemetry
from firmware.interfaces.parsed_telemetry import ParsedTelemetry


def parse_telemetry_line(line: str) -> ParsedTelemetry:
    parsed = ParsedTelemetry()
    for segment in line.strip().split(";"):
        tokens = segment.split()
        if not tokens:
            continue
        if tokens[0] == ImuTelemetry.TAG:
            imu = ImuTelemetry.from_tokens(tokens)
            if imu is not None:
                parsed.imu = imu
        elif tokens[0] == BatteryTelemetry.TAG:
            battery = BatteryTelemetry.from_tokens(tokens)
            if battery is not None:
                parsed.battery = battery
        else:
            joint = JointTelemetry.from_tokens(tokens)
            if joint is not None:
                parsed.joints.append(joint)
    return parsed
