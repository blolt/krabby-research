# SPDX-License-Identifier: BSD-3-Clause
"""Reference State Initialization for the crab hexapod (gait-formation-v2 Phase 1).

DeepMimic-style RSI (spin review section 5: "the one cheap mechanism class never tried"):
a fraction of env resets start FROM states sampled along the target gait instead of the
default stand, so schedule/phase-conditioned income is live from iteration 0 and the
policy's problem shifts from "find the gait" (exploration) to "keep it" (retention).

The bank is built offline from the Phase-0 scripted-gait walking stretch (setAB tripod,
this exact plant -- a dynamically-generated reference, not mocap): full joint state, root
height/orientation/velocity, and the gait-clock phase consistent with the reference's own
cam angles. The event stages the clock on the action term
(``rsi_clock_staged``); the action term's reset consumes it (events run BEFORE
action-manager reset in Isaac Lab's ``_reset_idx``).

Arm via ``KRABBY_RSI_FRAC`` (fraction of resets seeded, e.g. 0.15).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import torch

from isaaclab.utils.math import quat_apply

if TYPE_CHECKING:
    from isaaclab.envs import ManagerBasedEnv

_BANK_CACHE: dict[str, dict[str, torch.Tensor]] = {}


def _load_bank(path: str, device: str) -> dict[str, torch.Tensor]:
    key = f"{path}@{device}"
    if key not in _BANK_CACHE:
        raw = np.load(path)
        _BANK_CACHE[key] = {
            k: torch.as_tensor(raw[k], dtype=torch.float32, device=device)
            for k in ("joint_pos", "joint_vel", "root_quat_w", "root_z",
                      "root_lin_vel_b", "clock_phase")
        }
    return _BANK_CACHE[key]


def reset_from_reference_states(
    env: ManagerBasedEnv,
    env_ids: torch.Tensor,
    bank_path: str,
    fraction: float = 0.15,
) -> None:
    """Seed a Bernoulli subset of the resetting envs from the reference bank."""
    bank = _load_bank(bank_path, str(env.device))
    pick = torch.rand(len(env_ids), device=env.device) < fraction
    ids = env_ids[pick]
    if len(ids) == 0:
        return
    rows = torch.randint(0, bank["joint_pos"].shape[0], (len(ids),), device=env.device)

    robot = env.scene["robot"]
    # Root: keep each env's spawn XY (origin-relative), take z/orientation/velocity from
    # the reference. Bank linear velocity is body-frame; rotate to world.
    root_state = robot.data.default_root_state[ids].clone()
    root_state[:, 2] = bank["root_z"][rows]
    root_state[:, 3:7] = bank["root_quat_w"][rows]
    lin_w = quat_apply(bank["root_quat_w"][rows], bank["root_lin_vel_b"][rows])
    root_state[:, 7:10] = lin_w
    root_state[:, 10:13] = 0.0  # ang vel not recorded in the probe; ~0 in steady walking
    root_state[:, :2] += env.scene.env_origins[ids, :2]
    robot.write_root_pose_to_sim(root_state[:, :7], env_ids=ids)
    robot.write_root_velocity_to_sim(root_state[:, 7:], env_ids=ids)
    robot.write_joint_state_to_sim(
        bank["joint_pos"][rows], bank["joint_vel"][rows], env_ids=ids
    )
    # Stage the matching gait-clock phase; CrabHexDelayedJointPositionAction.reset consumes
    # it (and randomizes the non-staged envs as usual).
    action_term = env.action_manager.get_term("joint_pos")
    action_term.rsi_clock_staged[ids] = bank["clock_phase"][rows]
