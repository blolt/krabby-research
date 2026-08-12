"""Invalidate the stored IMU calibration so the next boot performs a fresh capture.

The firmware has no command for this: calibrate() returns Loaded when EEPROM holds
a valid record, so 1g.1's capture path is unreachable while one exists. A throwaway
sketch clears only the magic byte, then the real firmware is restored — joint
calibration (bytes 0-25) and role (32-33) are untouched.
"""
from __future__ import annotations

import os
import shutil
import subprocess

FQBN = "arduino:avr:mega"
_HERE = os.path.dirname(os.path.abspath(__file__))
_FIRMWARE = os.path.abspath(os.path.join(_HERE, ".."))
_CLEAR_SKETCH = os.path.join(_FIRMWARE, "bench_sketches", "imu_cal_clear")


def _cli() -> str:
    found = shutil.which("arduino-cli")
    if not found:
        raise RuntimeError("arduino-cli not on PATH")
    return found


def _run(args: list) -> None:
    subprocess.run(args, check=True, capture_output=True, text=True)


def invalidate(port: str) -> None:
    """Flash the clear sketch, then put the real firmware back."""
    cli = _cli()
    _run([cli, "compile", "--fqbn", FQBN, _CLEAR_SKETCH])
    _run([cli, "upload", "-p", port, "--fqbn", FQBN, _CLEAR_SKETCH])
    # make target handles library pinning and build properties (KRABBY_PIN_REV)
    _run(["make", "-C", _FIRMWARE, "upload-firmware", f"PORT={port}"])
