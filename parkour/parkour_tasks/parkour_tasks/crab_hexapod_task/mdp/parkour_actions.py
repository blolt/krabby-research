"""Crab-hex action terms (clip-before-history for last_action alignment; Go2 keeps shared behavior)."""

from __future__ import annotations

import torch
from collections.abc import Sequence
from typing import TYPE_CHECKING

from isaaclab.managers.action_manager import ActionTerm
from isaaclab.utils import configclass

from parkour_isaaclab.envs.mdp.parkour_actions import DelayedJointPositionActionCfg
from parkour_isaaclab.envs.mdp.parkour_actions.joint_actions import DelayedJointPositionAction

from parkour_tasks.crab_hexapod_task.mdp.crab_hex_cam_mapping import cam_shaft_to_hip

if TYPE_CHECKING:
    from isaaclab.envs import ManagerBasedEnv


class CrabHexDelayedJointPositionAction(DelayedJointPositionAction):
    """Clip policy actions before the delay buffer so ``last_action`` obs matches applied commands.

    Also drives the crab-hex cam mechanism's kinematic coupling (see plan): each leg's
    ``*_Body_CamShaft_RevoluteJoint`` is a real, PD-actuated DOF (part of this term's normal
    joint_names set); each leg's ``*_Body_Hip_RevoluteJoint`` has its own (high-gain) actuator
    (see crab_hex_scene_cfg.py) whose *position target* is computed from the shaft's current
    state via ``crab_hex_cam_mapping.cam_shaft_to_hip`` every physics substep.

    NOTE(cam-mechanism-migration): an earlier version of this coupling used
    ``Articulation.write_joint_state_to_sim`` (direct state teleportation) instead of a position
    target. That froze the *entire* articulation's dynamics -- including the completely separate
    floating-base chassis root, not just the targeted joint -- when called every substep
    (confirmed via A/B test: disabling the write alone restored normal free-fall). Repeatedly
    teleporting DOF state each substep is not how PhysX's articulation solver expects continuous
    control; ``set_joint_position_target`` (the same mechanism every other joint already uses) is
    the correct approach. Tracking is now approximate (real PD tracking error), not exact.
    """

    def __init__(self, cfg: DelayedJointPositionActionCfg, env: ManagerBasedEnv):
        super().__init__(cfg, env)
        # NOTE(cam-mechanism-migration): resolve CamShaft -> Body_Hip joint index pairs, one
        # pair per converted leg (starts at 1 leg in Phase A, grows to 6 in Phase C -- resolved
        # dynamically from whatever *_Body_CamShaft_RevoluteJoint joints exist in the loaded USD,
        # no code change needed as legs are propagated).
        shaft_ids, shaft_names = self._asset.find_joints([".*_Body_CamShaft_RevoluteJoint"], preserve_order=True)
        hip_names = [name.replace("_Body_CamShaft_RevoluteJoint", "_Body_Hip_RevoluteJoint") for name in shaft_names]
        hip_ids, _ = self._asset.find_joints(hip_names, preserve_order=True)
        self._cam_shaft_joint_ids = shaft_ids
        self._cam_hip_joint_ids = hip_ids
        # NOTE(cam-velocity-actions): the 6 camshaft action channels are VELOCITY targets
        # (rad/s), matching the real quick-return linkage whose motor spins continuously in
        # one direction. Their offset must be zero (default joint *velocity*), not the default
        # joint position that use_default_offset injects for the position channels.
        self._cam_action_cols = [
            i for i, name in enumerate(self._joint_names) if name in set(shaft_names)
        ]
        if self._cam_action_cols:
            self._offset[:, self._cam_action_cols] = 0.0

    def _clip_raw_actions(self, actions: torch.Tensor) -> torch.Tensor:
        if self.cfg.clip is None:
            return actions
        return torch.clamp(actions, min=self._clip[:, :, 0], max=self._clip[:, :, 1])

    def apply_actions(self):
        # Position targets for all 18 columns (inert for the camshaft: its actuator runs
        # stiffness=0, so the position term contributes no torque), then velocity targets on
        # the 6 cam columns — processed = raw * scale + 0 offset = rad/s.
        super().apply_actions()
        if self._cam_action_cols:
            self._asset.set_joint_velocity_target(
                self._processed_actions[:, self._cam_action_cols],
                joint_ids=self._cam_shaft_joint_ids,
            )
        if self._cam_shaft_joint_ids:
            theta_shaft = self._asset.data.joint_pos[:, self._cam_shaft_joint_ids]
            omega_shaft = self._asset.data.joint_vel[:, self._cam_shaft_joint_ids]
            # NOTE(cam-mechanism-migration): a freshly-added joint can transiently report
            # non-finite pos/vel from PhysX for the first substep or two before it fully settles
            # (observed at env reset). Sanitizing here is a hard guarantee we never feed NaN into
            # Body_Hip's position-target actuator below -- unlike an observation-level NaN (which
            # the repo already sanitizes and self-heals), a NaN position target would corrupt the
            # PD effort computation for that joint every subsequent step.
            if not torch.isfinite(theta_shaft).all() or not torch.isfinite(omega_shaft).all():
                theta_shaft = torch.nan_to_num(theta_shaft, nan=0.0, posinf=0.0, neginf=0.0)
                omega_shaft = torch.nan_to_num(omega_shaft, nan=0.0, posinf=0.0, neginf=0.0)
            theta_hip, omega_hip = cam_shaft_to_hip(theta_shaft, omega_shaft)
            self._asset.set_joint_position_target(theta_hip, joint_ids=self._cam_hip_joint_ids)
            # NOTE(cam-velocity-actions): also feed the linkage's velocity as a target — the
            # PD's damping term then acts as feedforward instead of braking against the
            # legitimate hip motion. Without it the hip lags/overshoots at the quick-return
            # velocity peak (~0.92x shaft speed) under continuous spin.
            self._asset.set_joint_velocity_target(omega_hip, joint_ids=self._cam_hip_joint_ids)

    def process_actions(self, actions: torch.Tensor):
        if self.env.common_step_counter % self._delay_update_global_steps == 0:
            if len(self._action_delay_steps) != 0:
                self.delay = torch.tensor(
                    self._action_delay_steps.pop(0), device=self.device, dtype=torch.float
                )
        clipped_actions = self._clip_raw_actions(actions)
        self._action_history_buf = torch.cat(
            [self._action_history_buf[:, 1:].clone(), clipped_actions[:, None, :].clone()], dim=1
        )
        indices = -1 - self.delay
        if self._use_delay:
            self._raw_actions[:] = self._action_history_buf[:, indices.long()]
        else:
            self._raw_actions[:] = clipped_actions
        self._processed_actions = self._raw_actions * self._scale + self._offset


@configclass
class CrabHexDelayedJointPositionActionCfg(DelayedJointPositionActionCfg):
    class_type: type[ActionTerm] = CrabHexDelayedJointPositionAction
