"""Pin the measured-hardware joint limits in ``assets/crab_simple.usda``.

Pure-text parse of the USD -- no Isaac Sim needed. Guards the 2026-08-13 geometry
alignment (hardware measurements: yaw +-28.5 deg cam-constrained, hip 35-160 deg from
straight-down vertical, knee 40-165 deg interior angle) against a silent revert by a
future asset regeneration. The right-leg (FR/MR/RR) knee limits are mirrored because
those joints carry a 180-degree frame flip (``localRot0 = (0, 0, 1, 0)``).

Conventions (see plan/campaign notes):
  hip:   sim = 90 deg - hw, positive = femur down  -> [-70, +55]
  knee L: interior = 90 deg - sim                  -> [-75, +50]
  knee R: sign-flipped frame                       -> [-50, +75]
  Body_Hip: passive, cam-slaved; hard +-32 so soft (0.9x) = +-28.8 > THETA_HIP_MAX
"""

import math
import re
from pathlib import Path

import pytest

USDA_PATH = Path(__file__).resolve().parents[2] / "assets" / "crab_simple.usda"

LEFT_LEGS = ("FL", "ML", "RL")
RIGHT_LEGS = ("FR", "MR", "RR")
ALL_LEGS = LEFT_LEGS + RIGHT_LEGS

# joint-name template -> {leg-prefix: (lower_deg, upper_deg)}
EXPECTED_LIMITS = {
    "{leg}_Body_Hip_RevoluteJoint": {leg: (-32.0, 32.0) for leg in ALL_LEGS},
    "{leg}_Hip_Femur_RevoluteJoint": {leg: (-70.0, 55.0) for leg in ALL_LEGS},
    "{leg}_Femur_Tibia_RevoluteJoint": {
        **{leg: (-75.0, 50.0) for leg in LEFT_LEGS},
        **{leg: (-50.0, 75.0) for leg in RIGHT_LEGS},
    },
}

# init-state defaults from crab_hex_scene_cfg.py (radians)
DEFAULTS_RAD = {
    "{leg}_Body_Hip_RevoluteJoint": {leg: 0.0 for leg in ALL_LEGS},
    "{leg}_Hip_Femur_RevoluteJoint": {leg: 0.30 for leg in ALL_LEGS},
    "{leg}_Femur_Tibia_RevoluteJoint": {
        **{leg: -0.07 for leg in LEFT_LEGS},
        **{leg: 0.10 for leg in RIGHT_LEGS},
    },
}

SOFT_LIMIT_FACTOR = 0.9  # crab_hex_scene_cfg.py soft_joint_pos_limit_factor
THETA_HIP_MAX = 0.4981432  # crab_hex_cam_mapping.py, asin(K)


def _parse_joint_blocks(text: str) -> dict[str, dict[str, float]]:
    """Return {joint_name: {attr: value}} for every PhysicsRevoluteJoint block."""
    blocks: dict[str, dict[str, float]] = {}
    pattern = re.compile(
        r'def PhysicsRevoluteJoint "(?P<name>\w+)".*?\{(?P<body>.*?)\n\s*\}',
        re.DOTALL,
    )
    for m in pattern.finditer(text):
        attrs: dict[str, float] = {}
        for lim in ("lowerLimit", "upperLimit"):
            lm = re.search(rf"physics:{lim} = (-?[\d.]+)", m.group("body"))
            if lm:
                attrs[lim] = float(lm.group(1))
        blocks[m.group("name")] = attrs
    return blocks


@pytest.fixture(scope="module")
def joint_blocks() -> dict[str, dict[str, float]]:
    return _parse_joint_blocks(USDA_PATH.read_text())


@pytest.mark.parametrize("template", sorted(EXPECTED_LIMITS))
def test_limits_match_hardware_table(joint_blocks, template):
    for leg, (lo, hi) in EXPECTED_LIMITS[template].items():
        name = template.format(leg=leg)
        assert name in joint_blocks, f"{name} missing from {USDA_PATH.name}"
        attrs = joint_blocks[name]
        assert attrs.get("lowerLimit") == pytest.approx(lo), f"{name} lowerLimit"
        assert attrs.get("upperLimit") == pytest.approx(hi), f"{name} upperLimit"


def test_cam_shaft_joints_are_continuous(joint_blocks):
    for leg in ALL_LEGS:
        name = f"{leg}_Body_CamShaft_RevoluteJoint"
        assert name in joint_blocks, f"{name} missing"
        attrs = joint_blocks[name]
        assert "lowerLimit" not in attrs and "upperLimit" not in attrs, (
            f"{name} must stay limit-free: the cam shaft spins continuously"
        )


def test_right_leg_knee_limits_mirror_left(joint_blocks):
    for left, right in zip(LEFT_LEGS, RIGHT_LEGS):
        l_attrs = joint_blocks[f"{left}_Femur_Tibia_RevoluteJoint"]
        r_attrs = joint_blocks[f"{right}_Femur_Tibia_RevoluteJoint"]
        assert r_attrs["lowerLimit"] == -l_attrs["upperLimit"]
        assert r_attrs["upperLimit"] == -l_attrs["lowerLimit"]


@pytest.mark.parametrize("template", sorted(EXPECTED_LIMITS))
def test_defaults_inside_soft_limits(joint_blocks, template):
    """soft_joint_pos_limit_factor scales the range about its midpoint."""
    for leg, (lo, hi) in EXPECTED_LIMITS[template].items():
        lo_r, hi_r = math.radians(lo), math.radians(hi)
        mid, half = (lo_r + hi_r) / 2, (hi_r - lo_r) / 2
        soft_lo = mid - SOFT_LIMIT_FACTOR * half
        soft_hi = mid + SOFT_LIMIT_FACTOR * half
        default = DEFAULTS_RAD[template][leg]
        assert soft_lo < default < soft_hi, (
            f"{template.format(leg=leg)} default {default} outside soft "
            f"[{soft_lo:.3f}, {soft_hi:.3f}]"
        )


def test_body_hip_soft_limit_clears_cam_sweep():
    """The passive Body_Hip soft limit must not clip the cam-slaved sweep."""
    soft = SOFT_LIMIT_FACTOR * math.radians(32.0)
    assert THETA_HIP_MAX < soft, (
        f"cam sweep {THETA_HIP_MAX:.4f} rad would be clipped by soft limit {soft:.4f}"
    )
