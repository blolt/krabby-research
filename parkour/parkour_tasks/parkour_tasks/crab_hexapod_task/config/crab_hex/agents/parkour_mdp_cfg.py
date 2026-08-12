import math

from isaaclab.envs.mdp.rewards import track_ang_vel_z_exp, track_lin_vel_xy_exp
from isaaclab.managers import ObservationGroupCfg as ObsGroup
from isaaclab.managers import ObservationTermCfg as ObsTerm
from isaaclab.managers import RewardTermCfg as RewTerm
from isaaclab.managers import SceneEntityCfg
from isaaclab.managers import TerminationTermCfg as DoneTerm
from isaaclab.utils import configclass
from isaaclab_tasks.manager_based.locomotion.velocity.mdp.rewards import feet_slide

from parkour_isaaclab.envs.mdp import rewards as mdp_rewards
from parkour_isaaclab.envs.mdp import terminations as parkour_terminations
from parkour_tasks.crab_hexapod_task.config.crab_hex.crab_hex_mdp_terminations import (
    terminate_crab_hex_failure,
)
from parkour_isaaclab.envs.mdp import observations as mdp_observations
from parkour_tasks.crab_hexapod_task.mdp.observations import (
    CrabHexObservationDeltaYawOk,
    CrabHexParkourObservations,
)
from parkour_tasks.crab_hexapod_task.mdp.parkour_actions import CrabHexDelayedJointPositionActionCfg
from parkour_tasks.extreme_parkour_task.config.go2.parkour_mdp_cfg import (
    ActionsCfg,
    CommandsCfg,
    EventCfg,
    ParkourEventsCfg,
)

# Leg order must match between tibia joints and footpads for stance-gated knee shaping.
_CRAB_TIBIA_JOINT_NAMES = [
    "FL_Femur_Tibia_RevoluteJoint",
    "FR_Femur_Tibia_RevoluteJoint",
    "ML_Femur_Tibia_RevoluteJoint",
    "MR_Femur_Tibia_RevoluteJoint",
    "RL_Femur_Tibia_RevoluteJoint",
    "RR_Femur_Tibia_RevoluteJoint",
]
_CRAB_FOOT_BODY_NAMES = [
    "FL_Footpad",
    "FR_Footpad",
    "ML_Footpad",
    "MR_Footpad",
    "RL_Footpad",
    "RR_Footpad",
]

# NOTE(cam-mechanism-migration): the 18 actually-actuated joints. Excludes
# *_Body_Hip_RevoluteJoint, which is now passive/kinematically-slaved to
# *_Body_CamShaft_RevoluteJoint (see crab_hex_cam_mapping.py) and must not receive a
# policy-commanded position target or appear in an unfiltered-sum reward (reward_dof_error,
# reward_torques).
_CRAB_ACTUATED_JOINT_NAMES = [
    ".*_Body_CamShaft_RevoluteJoint",
    ".*_Hip_Femur_RevoluteJoint",
    ".*_Femur_Tibia_RevoluteJoint",
]

@configclass
class CrabHexFlatWalkActionsCfg:
    """Flat-walk: scale 0.24 and ±1 raw clip (matches runner clip_actions)."""

    joint_pos = CrabHexDelayedJointPositionActionCfg(
        asset_name="robot",
        # NOTE(cam-mechanism-migration): see _CRAB_ACTUATED_JOINT_NAMES — excludes the now-passive
        # FL_Body_Hip_RevoluteJoint. Keeps action_dim == 18.
        joint_names=_CRAB_ACTUATED_JOINT_NAMES,
        scale=0.24,
        use_default_offset=True,
        action_delay_steps=[1, 1],
        delay_update_global_steps=24 * 8000,
        history_length=1,
        use_delay=False,
        clip={".*": (-1.0, 1.0)},
    )


@configclass
class CrabHexTeacherObservationsCfg:
    @configclass
    class PolicyCfg(ObsGroup):
        extreme_parkour_observations = ObsTerm(
            func=CrabHexParkourObservations,
            params={
                "asset_cfg": SceneEntityCfg("robot"),
                "sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*_Footpad"),
                "parkour_name": "base_parkour",
                "history_length": 10,
            },
            clip=(-100, 100),
        )

    policy: PolicyCfg = PolicyCfg()


@configclass
class CrabHexStudentActionsCfg(CrabHexFlatWalkActionsCfg):
    """Student distillation: same 0.24 / ±1 scale as 2b2 teacher."""

    def __post_init__(self):
        self.joint_pos.use_delay = True
        self.joint_pos.history_length = 8


@configclass
class CrabHexStudentObservationsCfg:
    """Crab hex student obs (depth + proprio); not inherited from Go2 ``StudentObservationsCfg``."""

    @configclass
    class PolicyCfg(ObsGroup):
        extreme_parkour_observations = ObsTerm(
            func=CrabHexParkourObservations,
            params={
                "asset_cfg": SceneEntityCfg("robot"),
                "sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*_Footpad"),
                "parkour_name": "base_parkour",
                "history_length": 10,
            },
            clip=(-100, 100),
        )

    @configclass
    class DepthCameraPolicyCfg(ObsGroup):
        depth_cam = ObsTerm(
            func=mdp_observations.image_features,
            params={
                "sensor_cfg": SceneEntityCfg("depth_camera"),
                "resize": (58, 87),
                "buffer_len": 2,
                "debug_vis": False,
            },
        )

    @configclass
    class DeltaYawOkPolicyCfg(ObsGroup):
        delta_yaw_ok = ObsTerm(
            func=CrabHexObservationDeltaYawOk,
            params={
                "parkour_name": "base_parkour",
                "threshold": 0.6,
            },
        )

    policy: PolicyCfg = PolicyCfg()
    depth_camera: DepthCameraPolicyCfg = DepthCameraPolicyCfg()
    delta_yaw_ok: DeltaYawOkPolicyCfg = DeltaYawOkPolicyCfg()


@configclass
class CrabHexRewardsCfg:
    """``KRABBY_HEX_TEACHER_MODE=full`` (default): Go2-style parkour — goal velocity primary."""

    reward_collision = RewTerm(
        func=mdp_rewards.reward_collision,
        weight=-6.0,
        params={
            "sensor_cfg": SceneEntityCfg(
                "contact_forces",
                # Include hip links: otherwise hip-on-terrain is not counted and the policy can
                # minimize torques by sitting on the hip (knees bent) with little collision signal.
                body_names=["body", ".*_Hip", ".*_Femur"],
            ),
        },
    )
    reward_feet_edge = RewTerm(
        func=mdp_rewards.reward_feet_edge,
        weight=-1.0,
        params={
            "asset_cfg": SceneEntityCfg("robot", body_names=".*_Footpad"),
            "sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*_Footpad"),
            "parkour_name": "base_parkour",
        },
    )
    # NOTE(cam-mechanism-migration): filtered to the 18 actuated joints -- excludes the now-passive
    # *_Body_Hip_RevoluteJoint (kinematically-slaved to *_Body_CamShaft_RevoluteJoint, see
    # crab_hex_cam_mapping.py), whose "torque"/dof-error is meaningless (not force/PD-commanded
    # by the policy).
    reward_torques = RewTerm(
        func=mdp_rewards.reward_torques,
        weight=-0.00001,
        params={"asset_cfg": SceneEntityCfg("robot", joint_names=_CRAB_ACTUATED_JOINT_NAMES)},
    )
    reward_dof_error = RewTerm(
        func=mdp_rewards.reward_dof_error,
        weight=-0.04,
        params={"asset_cfg": SceneEntityCfg("robot", joint_names=_CRAB_ACTUATED_JOINT_NAMES)},
    )
    reward_hip_pos = RewTerm(
        func=mdp_rewards.reward_hip_pos,
        weight=-0.5,
        params={"asset_cfg": SceneEntityCfg("robot", joint_names=[".*_Body_Hip_RevoluteJoint"])},
    )
    # NOTE(cam-mechanism-migration): see CrabHexFlatWalkRewardsCfg.penalty_motor_direction_reversal
    # for full rationale -- same medium-weight penalty, added here so it propagates to every
    # teacher-stage subclass (Warmup/Bridge/2b1/2b2) that doesn't re-override it.
    penalty_motor_direction_reversal = RewTerm(
        func=mdp_rewards.PenaltyMotorDirectionReversal,
        weight=-0.3,
        params={"asset_cfg": SceneEntityCfg("robot", joint_names=[".*_Body_CamShaft_RevoluteJoint"])},
    )
    # NOTE(stride-length): see CrabHexFlatWalkRewardsCfg.reward_stride_length for full rationale
    # -- same starting weight/power, added here so it propagates to every teacher-stage subclass
    # (Warmup/Bridge/2b1/2b2) that doesn't re-override it.
    reward_stride_length = RewTerm(
        func=mdp_rewards.RewardStrideLength,
        weight=0.5,
        params={
            "asset_cfg": SceneEntityCfg("robot"),
            "sensor_cfg": SceneEntityCfg("contact_forces", body_names=_CRAB_FOOT_BODY_NAMES, preserve_order=True),
            "command_name": "base_velocity",
            "power": 2.0,
            # NOTE(stride-length-v3): redefined to reward stance-phase body progress along the
            # commanded direction, not joint-space (hip-yaw) movement, and dropped swing-phase
            # reward entirely -- a foot in the air can't push the robot, so it shouldn't be
            # rewarded for moving. This also structurally eliminates the v2 snap exploit (a leg
            # covering its whole joint range in a single 20ms physics step): that exploit relied on
            # swing-phase joint displacement being rewarded regardless of whether the robot actually
            # moved, and swing is no longer rewarded at all, so the earlier velocity_cost_weight/
            # _power terms are no longer needed. min_phase_duration still guards against a spurious
            # one-step contact reading being trusted as a real stance. (v4, per-foot signed
            # touchdown displacement, was tried and reverted -- see
            # sim_fine_tuning/2026-08-09_0106_stride_length_v4/CHANGELOG.md.)
            "min_phase_duration": 0.1,
            "min_cmd_norm": 0.12,
        },
    )
    reward_ang_vel_xy = RewTerm(
        func=mdp_rewards.reward_ang_vel_xy,
        weight=-0.05,
        params={"asset_cfg": SceneEntityCfg("robot")},
    )
    # NOTE(teacher-carry-up): -0.1 -> -0.3, matching the flat-walk campaign's baked winner
    # (sim_fine_tuning/2026-08-09_0920_short_runs/CHANGELOG.md) after the T0/T1/T2 teacher-stack
    # screening study picked T2 (this weight kept, reversal penalty unchanged) over the control
    # and the full-mirror arm -- see sim_fine_tuning/2026-08-09_1526_gait_tuned/CHANGELOG.md.
    reward_action_rate = RewTerm(
        func=mdp_rewards.reward_action_rate,
        weight=-0.3,
        params={"asset_cfg": SceneEntityCfg("robot")},
    )
    reward_dof_acc = RewTerm(
        func=mdp_rewards.reward_dof_acc,
        weight=-2.5e-7,
        params={"asset_cfg": SceneEntityCfg("robot")},
    )
    reward_lin_vel_z = RewTerm(
        func=mdp_rewards.reward_lin_vel_z,
        weight=-1.0,
        params={
            "asset_cfg": SceneEntityCfg("robot"),
            "parkour_name": "base_parkour",
        },
    )
    reward_orientation = RewTerm(
        func=mdp_rewards.reward_orientation,
        weight=-1.0,
        params={
            "asset_cfg": SceneEntityCfg("robot"),
            "parkour_name": "base_parkour",
        },
    )
    reward_feet_stumble = RewTerm(
        func=mdp_rewards.reward_feet_stumble,
        weight=-1.0,
        params={"sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*_Footpad")},
    )
    reward_tracking_goal_vel = RewTerm(
        func=mdp_rewards.reward_tracking_goal_vel,
        weight=2.25,
        params={"asset_cfg": SceneEntityCfg("robot"), "parkour_name": "base_parkour"},
    )
    reward_tracking_yaw = RewTerm(
        func=mdp_rewards.reward_tracking_yaw,
        weight=0.5,
        params={"asset_cfg": SceneEntityCfg("robot"), "parkour_name": "base_parkour"},
    )
    # NOTE(teacher-carry-up): -1e-7 -> -1e-6, see reward_action_rate's note above.
    reward_delta_torques = RewTerm(
        func=mdp_rewards.reward_delta_torques,
        weight=-1.0e-6,
        params={"asset_cfg": SceneEntityCfg("robot")},
    )


@configclass
class CrabHexTeacherWarmupRewardsCfg(CrabHexRewardsCfg):
    """Stage-2 bridge: softer contact penalties, parkour goals, and flat-walk velocity tracking."""

    reward_collision = RewTerm(
        func=mdp_rewards.reward_collision,
        weight=-2.0,
        params={
            "sensor_cfg": SceneEntityCfg(
                "contact_forces",
                body_names=["body", ".*_Hip", ".*_Femur"],
            ),
        },
    )
    reward_feet_edge = RewTerm(
        func=mdp_rewards.reward_feet_edge,
        weight=-0.3,
        params={
            "asset_cfg": SceneEntityCfg("robot", body_names=".*_Footpad"),
            "sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*_Footpad"),
            "parkour_name": "base_parkour",
        },
    )
    track_lin_vel_xy_exp = RewTerm(
        func=track_lin_vel_xy_exp,
        weight=1.25,
        params={"command_name": "base_velocity", "std": math.sqrt(0.02)},
    )
    track_ang_vel_z_exp = RewTerm(
        func=track_ang_vel_z_exp,
        weight=1.0,
        params={"command_name": "base_velocity", "std": math.sqrt(0.25)},
    )
    penalty_lin_vel_y = RewTerm(
        func=mdp_rewards.penalty_lin_vel_y_l2,
        weight=-3.0,
        params={"command_name": "base_velocity", "asset_cfg": SceneEntityCfg("robot")},
    )


@configclass
class CrabHexTeacherBridgeRewardsCfg(CrabHexTeacherWarmupRewardsCfg):
    """``KRABBY_HEX_TEACHER_MODE=bridge``: easy mixed walk — velocity/posture primary, parkour goal/yaw off."""

    reward_hip_pos = RewTerm(
        func=mdp_rewards.reward_hip_pos,
        weight=0.0,
        params={"asset_cfg": SceneEntityCfg("robot", joint_names=[".*_Body_Hip_RevoluteJoint"])},
    )
    reward_tracking_goal_vel = RewTerm(
        func=mdp_rewards.reward_tracking_goal_vel_on_parkour,
        weight=0.0,
        params={"asset_cfg": SceneEntityCfg("robot"), "parkour_name": "base_parkour"},
    )
    reward_tracking_yaw = RewTerm(
        func=mdp_rewards.reward_tracking_yaw,
        weight=0.0,
        params={"asset_cfg": SceneEntityCfg("robot"), "parkour_name": "base_parkour"},
    )
    track_lin_vel_xy_exp = RewTerm(
        func=track_lin_vel_xy_exp,
        weight=2.2,
        params={"command_name": "base_velocity", "std": math.sqrt(0.02)},
    )
    track_ang_vel_z_exp = RewTerm(
        func=track_ang_vel_z_exp,
        weight=0.0,
        params={"command_name": "base_velocity", "std": math.sqrt(0.25)},
    )
    reward_forward_progress_along_command = RewTerm(
        func=mdp_rewards.reward_forward_progress_along_command,
        weight=0.4,
        params={
            "command_name": "base_velocity",
            "asset_cfg": SceneEntityCfg("robot"),
            "min_cmd_norm": 0.12,
            "max_speed_scale": 1.75,
        },
    )
    reward_orientation = RewTerm(
        func=mdp_rewards.reward_orientation_upright,
        weight=-3.0,
        params={
            "asset_cfg": SceneEntityCfg("robot"),
            "parkour_name": "base_parkour",
        },
    )
    penalty_base_pitch_forward_linear = RewTerm(
        func=mdp_rewards.penalty_base_pitch_forward_linear,
        weight=-2.5,
        params={
            "command_name": "base_velocity",
            "asset_cfg": SceneEntityCfg("robot"),
            "min_forward_speed_cmd": 0.12,
        },
    )
    penalty_low_forward_speed_when_commanded = RewTerm(
        func=mdp_rewards.penalty_low_forward_speed_when_commanded,
        weight=-3.0,
        params={
            "command_name": "base_velocity",
            "asset_cfg": SceneEntityCfg("robot"),
            "min_forward_speed_cmd": 0.12,
            "min_actual_speed": 0.35,
        },
    )
    reward_feet_air_time_on_flat = RewTerm(
        func=mdp_rewards.reward_feet_air_time_on_flat,
        weight=0.5,
        params={
            "command_name": "base_velocity",
            "sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*_Footpad"),
            "parkour_name": "base_parkour",
            "threshold": 0.05,
        },
    )
    reward_forward_speed_on_flat = RewTerm(
        func=mdp_rewards.reward_forward_speed_on_flat,
        weight=0.7,
        params={
            "command_name": "base_velocity",
            "asset_cfg": SceneEntityCfg("robot"),
            "parkour_name": "base_parkour",
            "min_forward_speed_cmd": 0.12,
            "target_speed": 0.55,
            "max_bonus_speed": 0.85,
        },
    )
    penalty_backward_along_command = RewTerm(
        func=mdp_rewards.penalty_backward_along_command,
        weight=-1.5,
        params={
            "command_name": "base_velocity",
            "asset_cfg": SceneEntityCfg("robot"),
            "min_forward_speed_cmd": 0.12,
        },
    )
    penalty_body_heading_error_l2 = RewTerm(
        func=mdp_rewards.penalty_body_heading_error_l2,
        weight=-1.5,
        params={
            "command_name": "base_velocity",
            "asset_cfg": SceneEntityCfg("robot"),
            "min_forward_speed_cmd": 0.12,
        },
    )


@configclass
class CrabHexStage2BPhase1RewardsCfg(CrabHexTeacherBridgeRewardsCfg):
    """``KRABBY_HEX_TEACHER_MODE=2b1``: hybrid walk — bridge core + weak goal_vel (0.75) / yaw (0.2) aux."""

    reward_tracking_goal_vel = RewTerm(
        func=mdp_rewards.reward_tracking_goal_vel,
        weight=0.75,
        params={"asset_cfg": SceneEntityCfg("robot"), "parkour_name": "base_parkour"},
    )
    reward_tracking_yaw = RewTerm(
        func=mdp_rewards.reward_tracking_yaw,
        weight=0.2,
        params={"asset_cfg": SceneEntityCfg("robot"), "parkour_name": "base_parkour"},
    )
    reward_hip_pos = RewTerm(
        func=mdp_rewards.reward_hip_pos,
        weight=-0.5,
        params={"asset_cfg": SceneEntityCfg("robot", joint_names=[".*_Body_Hip_RevoluteJoint"])},
    )
    reward_feet_stumble = RewTerm(
        func=mdp_rewards.reward_feet_stumble,
        weight=-1.0,
        params={"sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*_Footpad")},
    )
    reward_lin_vel_z = RewTerm(
        func=mdp_rewards.reward_lin_vel_z,
        weight=-1.0,
        params={"asset_cfg": SceneEntityCfg("robot"), "parkour_name": "base_parkour"},
    )
    reward_ang_vel_xy = RewTerm(
        func=mdp_rewards.reward_ang_vel_xy,
        weight=-0.05,
        params={"asset_cfg": SceneEntityCfg("robot")},
    )
    # NOTE(teacher-carry-up): -0.1 -> -0.3, covers 2b1 and 2b2 (Stage2BPhase2RewardsCfg inherits
    # from this class without re-declaring). See CrabHexRewardsCfg.reward_action_rate's note.
    reward_action_rate = RewTerm(
        func=mdp_rewards.reward_action_rate,
        weight=-0.3,
        params={"asset_cfg": SceneEntityCfg("robot")},
    )
    reward_dof_error = RewTerm(
        func=mdp_rewards.reward_dof_error,
        weight=-0.04,
        params={"asset_cfg": SceneEntityCfg("robot", joint_names=_CRAB_ACTUATED_JOINT_NAMES)},
    )
    reward_torques = RewTerm(
        func=mdp_rewards.reward_torques,
        weight=-0.00001,
        params={"asset_cfg": SceneEntityCfg("robot", joint_names=_CRAB_ACTUATED_JOINT_NAMES)},
    )
    reward_dof_acc = RewTerm(
        func=mdp_rewards.reward_dof_acc,
        weight=-2.5e-7,
        params={"asset_cfg": SceneEntityCfg("robot")},
    )
    # NOTE(teacher-carry-up): -1e-7 -> -1e-6, see reward_action_rate's note above.
    reward_delta_torques = RewTerm(
        func=mdp_rewards.reward_delta_torques,
        weight=-1.0e-6,
        params={"asset_cfg": SceneEntityCfg("robot")},
    )


@configclass
class CrabHexStage2BPhase2RewardsCfg(CrabHexStage2BPhase1RewardsCfg):
    """``KRABBY_HEX_TEACHER_MODE=2b2`` teacher-ready (phase 2): obstacle-walk for distillation.

    Global clearance +1.8, foot swing +2.0, swing-vz +0.4, recover +0.4; forward +0.25.
    Micro-swing penalty −0.2; anti-stall −0.8. Bridge velocity-primary aux zeroed.
    """

    # --- Zero bridge-primary aux (not in teacher-ready stack) ---
    track_lin_vel_xy_exp = RewTerm(
        func=track_lin_vel_xy_exp,
        weight=0.0,
        params={"command_name": "base_velocity", "std": math.sqrt(0.02)},
    )
    penalty_lin_vel_y = RewTerm(
        func=mdp_rewards.penalty_lin_vel_y_l2,
        weight=0.0,
        params={"command_name": "base_velocity", "asset_cfg": SceneEntityCfg("robot")},
    )
    penalty_base_pitch_forward_linear = RewTerm(
        func=mdp_rewards.penalty_base_pitch_forward_linear,
        weight=0.0,
        params={
            "command_name": "base_velocity",
            "asset_cfg": SceneEntityCfg("robot"),
            "min_forward_speed_cmd": 0.12,
        },
    )
    penalty_low_forward_speed_when_commanded = RewTerm(
        func=mdp_rewards.penalty_low_forward_speed_when_commanded,
        weight=-0.8,
        params={
            "command_name": "base_velocity",
            "asset_cfg": SceneEntityCfg("robot"),
            "min_forward_speed_cmd": 0.12,
            "min_actual_speed": 0.35,
        },
    )
    reward_feet_air_time_on_flat = RewTerm(
        func=mdp_rewards.reward_feet_air_time_on_flat,
        weight=0.0,
        params={
            "command_name": "base_velocity",
            "sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*_Footpad"),
            "parkour_name": "base_parkour",
            "threshold": 0.05,
        },
    )
    reward_forward_speed_on_flat = RewTerm(
        func=mdp_rewards.reward_forward_speed_on_flat,
        weight=0.0,
        params={
            "command_name": "base_velocity",
            "asset_cfg": SceneEntityCfg("robot"),
            "parkour_name": "base_parkour",
            "min_forward_speed_cmd": 0.12,
            "target_speed": 0.55,
            "max_bonus_speed": 0.85,
        },
    )
    penalty_backward_along_command = RewTerm(
        func=mdp_rewards.penalty_backward_along_command,
        weight=0.0,
        params={
            "command_name": "base_velocity",
            "asset_cfg": SceneEntityCfg("robot"),
            "min_forward_speed_cmd": 0.12,
        },
    )
    penalty_body_heading_error_l2 = RewTerm(
        func=mdp_rewards.penalty_body_heading_error_l2,
        weight=0.0,
        params={
            "command_name": "base_velocity",
            "asset_cfg": SceneEntityCfg("robot"),
            "min_forward_speed_cmd": 0.12,
        },
    )
    reward_tracking_yaw_on_parkour = RewTerm(
        func=mdp_rewards.reward_tracking_yaw_on_parkour,
        weight=0.0,
        params={
            "asset_cfg": SceneEntityCfg("robot"),
            "parkour_name": "base_parkour",
            "command_name": "base_velocity",
            "min_forward_speed_cmd": 0.12,
        },
    )

    # --- Teacher-ready stack ---
    reward_forward_progress_along_command = RewTerm(
        func=mdp_rewards.reward_forward_progress_along_command,
        weight=0.25,
        params={
            "command_name": "base_velocity",
            "asset_cfg": SceneEntityCfg("robot"),
            "min_cmd_norm": 0.12,
            "max_speed_scale": 1.75,
        },
    )
    reward_obstacle_clearance = RewTerm(
        func=mdp_rewards.reward_obstacle_clearance,
        weight=1.8,
        params={
            "asset_cfg": SceneEntityCfg("robot"),
            "sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*_Footpad"),
            "parkour_name": "base_parkour",
            "command_name": "base_velocity",
            "min_goal_progress": 0.15,
            "min_forward_speed": 0.25,
            "min_forward_speed_cmd": 0.12,
            "max_tilt_gravity_xy_sq": 0.02,
        },
    )
    reward_foot_clearance = RewTerm(
        func=mdp_rewards.reward_foot_clearance,
        weight=2.0,
        params={
            "asset_cfg": SceneEntityCfg("robot", body_names=".*_Footpad"),
            "sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*_Footpad"),
            "command_name": "base_velocity",
            "contact_force_threshold": 0.1,
            "min_clearance_m": 0.05,
            "max_clearance_m": 0.20,
            "min_forward_speed_cmd": 0.12,
            "ground_offset_from_root_m": -1.0,
            "parkour_name": "base_parkour",
        },
    )
    reward_recover_from_stall = RewTerm(
        func=mdp_rewards.RewardRecoverFromStall,
        weight=0.2,
        params={
            "asset_cfg": SceneEntityCfg("robot"),
            "sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*_Footpad"),
            "parkour_name": "base_parkour",
            "command_name": "base_velocity",
            "min_forward_speed_cmd": 0.12,
            "min_actual_speed": 0.15,
            "stuck_contact_force": 15.0,
            "min_other_feet_loaded": 2,
            "max_tilt_gravity_xy_sq": 0.04,
        },
    )
    penalty_swing_min_clearance = RewTerm(
        func=mdp_rewards.penalty_swing_min_clearance,
        weight=-0.4,
        params={
            "asset_cfg": SceneEntityCfg("robot", body_names=".*_Footpad"),
            "sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*_Footpad"),
            "command_name": "base_velocity",
            "contact_force_threshold": 0.1,
            "min_clearance_m": 0.03,
            "min_forward_speed_cmd": 0.12,
            "ground_offset_from_root_m": -1.0,
            "parkour_name": "base_parkour",
        },
    )
    reward_swing_vertical_vel = RewTerm(
        func=mdp_rewards.RewardSwingVerticalVel,
        weight=0.8,
        params={
            "asset_cfg": SceneEntityCfg("robot", body_names=".*_Footpad"),
            "sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*_Footpad"),
            "parkour_name": "base_parkour",
            "command_name": "base_velocity",
            "contact_force_threshold": 0.1,
            "min_forward_speed_cmd": 0.12,
            "max_vertical_vel": 0.5,
            "ground_offset_from_root_m": -1.0,
        },
    )
    reward_tracking_goal_vel = RewTerm(
        func=mdp_rewards.reward_tracking_goal_vel,
        weight=1.0,
        params={"asset_cfg": SceneEntityCfg("robot"), "parkour_name": "base_parkour"},
    )
    reward_tracking_yaw = RewTerm(
        func=mdp_rewards.reward_tracking_yaw,
        weight=0.3,
        params={"asset_cfg": SceneEntityCfg("robot"), "parkour_name": "base_parkour"},
    )
    reward_collision = RewTerm(
        func=mdp_rewards.reward_collision,
        weight=-3.0,
        params={
            "sensor_cfg": SceneEntityCfg(
                "contact_forces",
                body_names=["body", ".*_Hip", ".*_Femur"],
            ),
        },
    )
    reward_feet_edge = RewTerm(
        func=mdp_rewards.reward_feet_edge,
        weight=-0.8,
        params={
            "asset_cfg": SceneEntityCfg("robot", body_names=".*_Footpad"),
            "sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*_Footpad"),
            "parkour_name": "base_parkour",
        },
    )
    reward_feet_stumble = RewTerm(
        func=mdp_rewards.reward_feet_stumble,
        weight=-0.8,
        params={"sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*_Footpad")},
    )
    reward_orientation = RewTerm(
        func=mdp_rewards.reward_orientation,
        weight=-1.0,
        params={
            "asset_cfg": SceneEntityCfg("robot"),
            "parkour_name": "base_parkour",
        },
    )


@configclass
class CrabHexFlatWalkRewardsCfg:
    """Stage 1 **gait** rewards (``Isaac-Crab-Hex-Flat-Walk-v0``): speed + posture + footfall shaping; no parkour goals."""

    track_lin_vel_xy_exp = RewTerm(
        func=track_lin_vel_xy_exp,
        weight=1.25,
        params={"command_name": "base_velocity", "std": math.sqrt(0.02)},
    )
    track_ang_vel_z_exp = RewTerm(
        func=track_ang_vel_z_exp,
        weight=1.0,
        params={"command_name": "base_velocity", "std": math.sqrt(0.25)},
    )
    penalty_lin_vel_y = RewTerm(
        func=mdp_rewards.penalty_lin_vel_y_l2,
        weight=-3.0,
        params={"command_name": "base_velocity", "asset_cfg": SceneEntityCfg("robot")},
    )
    reward_forward_progress_along_command = RewTerm(
        func=mdp_rewards.reward_forward_progress_along_command,
        weight=0.60,
        params={
            "command_name": "base_velocity",
            "asset_cfg": SceneEntityCfg("robot"),
            "min_cmd_norm": 0.12,
            "max_speed_scale": 1.75,
        },
    )
    reward_orientation = RewTerm(
        func=mdp_rewards.reward_orientation,
        weight=-0.7,
        params={
            "asset_cfg": SceneEntityCfg("robot"),
            "parkour_name": "base_parkour",
        },
    )
    # NOTE(tripod-stability-campaign): registered at weight 0.0 (inert) so it's Hydra-sweepable.
    # reward_orientation is direction-blind (roll^2+pitch^2); this term is signed and forward-gated,
    # so it's the only lever that can target the sustained ~12deg nose-down lean measured on the
    # baseline checkpoint (see sim_fine_tuning/2026-08-10_0058_tripod_stability/RESULTS.md).
    penalty_base_pitch_forward_linear = RewTerm(
        func=mdp_rewards.penalty_base_pitch_forward_linear,
        weight=0.0,
        params={
            "command_name": "base_velocity",
            "asset_cfg": SceneEntityCfg("robot"),
            "min_forward_speed_cmd": 0.12,
        },
    )
    # NOTE(tripod-stability-campaign): the explicit contact-schedule reward from Task 1 §2.3,
    # registered at weight 0.0 (inert). None of the config-only knobs tried in
    # sim_fine_tuning/2026-08-10_0058_tripod_stability/ moved tripod_score, so this term rewards
    # genuine tripod-set alternation directly -- see crab_hex_tripod_reward.py for the full math.
    # v4 replaced all state-based income (v2's support bonus, v3's v_z stability gate) with an
    # event-based swap credit after four from-scratch failures showed every state-paying variant
    # gets farmed by a cheap state-holding gait (lunge/tip-rock/skate/drag) -- see the v1-v4
    # addenda in crab_hex_tripod_reward.py and the campaign RESULTS.md.
    reward_tripod_schedule = RewTerm(
        func=mdp_rewards.RewardTripodSchedule,
        weight=0.0,
        params={
            "sensor_cfg": SceneEntityCfg("contact_forces", body_names=_CRAB_FOOT_BODY_NAMES, preserve_order=True),
            "command_name": "base_velocity",
            "min_cmd_norm": 0.12,
            "debounce_s": 0.08,
            "min_swap_interval": 0.1,
            "max_hold_s": 0.6,
            "swap_credit": 15.0,
        },
    )
    reward_lin_vel_z = RewTerm(
        func=mdp_rewards.reward_lin_vel_z,
        weight=-0.15,
        params={
            "asset_cfg": SceneEntityCfg("robot"),
            "parkour_name": "base_parkour",
        },
    )
    reward_ang_vel_xy = RewTerm(
        func=mdp_rewards.reward_ang_vel_xy,
        weight=0.0,
        params={"asset_cfg": SceneEntityCfg("robot")},
    )
    reward_dof_error = RewTerm(
        func=mdp_rewards.reward_dof_error,
        weight=0.0,
        # NOTE(cam-mechanism-migration): filtered to the actuated joints so the (currently
        # zero-weight, but still logged) sum doesn't include the passive FL_Body_Hip_RevoluteJoint.
        params={"asset_cfg": SceneEntityCfg("robot", joint_names=_CRAB_ACTUATED_JOINT_NAMES)},
    )
    # NOTE(short-run-campaign): weight raised 0.40 -> 0.8, the winning value from the Milestone 18
    # Task 1 short-run tuning campaign (sim_fine_tuning/2026-08-09_0920_short_runs/CHANGELOG.md) -- threshold=0.05
    # itself was swept (0.10, 0.15) and found not to move gait quality on its own, so it stays at
    # default. Improves tippy_tap and measured stride together vs the untouched v3 baseline.
    reward_feet_air_time_positive = RewTerm(
        func=mdp_rewards.reward_feet_air_time_positive,
        weight=0.8,
        params={
            "command_name": "base_velocity",
            "sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*_Footpad"),
            "threshold": 0.05,
        },
    )
    # NOTE(stride-length): rewards |hip-yaw diff|**power across every touchdown<->liftoff
    # transition (both swing- and stance-phase leg movement) -- convex (power=2) so a single
    # long stride outscores several short ones covering the same net range, directly targeting
    # the "tippy-tap" micro-stepping pattern the gait-eval harness flags across every checkpoint
    # tested so far. Starting weight/power, tune against the harness (Milestone 18 Task 1).
    reward_stride_length = RewTerm(
        func=mdp_rewards.RewardStrideLength,
        weight=0.5,
        params={
            "asset_cfg": SceneEntityCfg("robot"),
            "sensor_cfg": SceneEntityCfg("contact_forces", body_names=_CRAB_FOOT_BODY_NAMES, preserve_order=True),
            "command_name": "base_velocity",
            "power": 2.0,
            # NOTE(stride-length-v3): redefined to reward stance-phase body progress along the
            # commanded direction, not joint-space (hip-yaw) movement, and dropped swing-phase
            # reward entirely -- a foot in the air can't push the robot, so it shouldn't be
            # rewarded for moving. This also structurally eliminates the v2 snap exploit (a leg
            # covering its whole joint range in a single 20ms physics step): that exploit relied on
            # swing-phase joint displacement being rewarded regardless of whether the robot actually
            # moved, and swing is no longer rewarded at all, so the earlier velocity_cost_weight/
            # _power terms are no longer needed. min_phase_duration still guards against a spurious
            # one-step contact reading being trusted as a real stance. (v4, per-foot signed
            # touchdown displacement, was tried and reverted -- see
            # sim_fine_tuning/2026-08-09_0106_stride_length_v4/CHANGELOG.md.)
            "min_phase_duration": 0.1,
            "min_cmd_norm": 0.12,
        },
    )
    penalty_tibia_deviation_in_stance = RewTerm(
        func=mdp_rewards.penalty_joint_deviation_when_in_contact,
        weight=-0.28,
        params={
            "asset_cfg": SceneEntityCfg(
                "robot",
                joint_names=_CRAB_TIBIA_JOINT_NAMES,
                preserve_order=True,
            ),
            "sensor_cfg": SceneEntityCfg(
                "contact_forces",
                body_names=_CRAB_FOOT_BODY_NAMES,
                preserve_order=True,
            ),
            "contact_force_threshold": 0.1,
        },
    )
    penalty_foot_idle_when_forward = RewTerm(
        func=mdp_rewards.PenaltyFootIdleWhenForward,
        weight=-0.12,
        params={
            "command_name": "base_velocity",
            "sensor_cfg": SceneEntityCfg(
                "contact_forces",
                body_names=_CRAB_FOOT_BODY_NAMES,
                preserve_order=True,
            ),
            "max_idle_steps": 60,
            "contact_force_threshold": 0.1,
            "min_forward_speed_cmd": 0.12,
        },
    )
    penalty_excess_feet_contact_forward = RewTerm(
        func=mdp_rewards.penalty_excess_feet_in_contact_forward,
        weight=-0.20,
        params={
            "command_name": "base_velocity",
            "sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*_Footpad"),
            "max_feet_on_ground": 4,
            "contact_force_threshold": 0.1,
            "min_forward_speed_cmd": 0.12,
        },
    )
    reward_stance_support_feet_when_forward = RewTerm(
        func=mdp_rewards.reward_stance_support_feet_when_forward,
        weight=0.0,
        params={
            "command_name": "base_velocity",
            "sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*_Footpad"),
            "min_feet_loaded": 3,
            "contact_force_threshold": 0.1,
            "min_forward_speed_cmd": 0.12,
        },
    )
    feet_slide = RewTerm(
        func=feet_slide,
        weight=0.0,
        params={
            "sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*_Footpad"),
            "asset_cfg": SceneEntityCfg("robot", body_names=".*_Footpad"),
        },
    )
    reward_collision = RewTerm(
        func=mdp_rewards.reward_collision,
        weight=0.0,
        params={
            "sensor_cfg": SceneEntityCfg(
                "contact_forces",
                body_names=["body", ".*_Hip", ".*_Femur"],
            ),
        },
    )
    # NOTE(cam-mechanism-migration, superseded by short-run-campaign): originally penalized the
    # cam-shaft motor reversing rotational direction at weight=-0.3. The Milestone 18 Task 1
    # short-run campaign (sim_fine_tuning/2026-08-09_0920_short_runs/CHANGELOG.md) ran a 3-arm study testing this
    # mechanism against general action-smoothness terms for the same goal (suppressing
    # high-frequency reversals): retuning this weight alone (-0.15, -0.6) never beat the
    # air-time-only baseline, but turning it OFF and using reward_action_rate/reward_delta_torques
    # instead (below) was the single best result of the whole campaign -- best tippy_tap AND best
    # measured stride simultaneously, at both 1000 and 2000 iterations. Weight zeroed accordingly;
    # left registered (not deleted) so it can be reintroduced if the smoothness-only route proves
    # insufficient once carried up the teacher stack, where reversal count remains a real
    # hardware-longevity concern documented in motor_reversal_on/CHANGELOG.md.
    penalty_motor_direction_reversal = RewTerm(
        func=mdp_rewards.PenaltyMotorDirectionReversal,
        weight=0.0,
        params={"asset_cfg": SceneEntityCfg("robot", joint_names=[".*_Body_CamShaft_RevoluteJoint"])},
    )
    # NOTE(short-run-campaign): weights raised from 0.0 (previously inactive on flat-walk, only
    # used in the teacher-stage rewards above) to the winning values from the 3-arm study
    # described above -- see sim_fine_tuning/2026-08-09_0920_short_runs/CHANGELOG.md for the full comparison.
    # Combined with reward_feet_air_time_positive=0.8 and penalty_motor_direction_reversal=0.0,
    # this config cleared every Task 1 §1c/§1f target at a 2000-iteration validation: tippy_tap
    # 19.09%->13.39% (<= baseline's 13.5%), measured stride 0.178m->0.1975m (best of the entire
    # Task 1 comparison series), schedule_completion_rate steady at 100%. Training-time tracking
    # error was somewhat elevated in testing (policy trades a little velocity-tracking precision
    # for smoother actions) but did not show up as a gait-eval regression on flat-walk -- worth
    # watching if this config is carried up the teacher stack.
    reward_action_rate = RewTerm(
        func=mdp_rewards.reward_action_rate,
        weight=-0.3,
        params={"asset_cfg": SceneEntityCfg("robot")},
    )
    reward_delta_torques = RewTerm(
        func=mdp_rewards.reward_delta_torques,
        weight=-1e-6,
        params={"asset_cfg": SceneEntityCfg("robot")},
    )


@configclass
class CrabHexFlatWalkTerminationsCfg:
    """Relaxed terminations for flat-walk pretraining."""

    total_terminates = DoneTerm(
        func=parkour_terminations.terminate_episode,
        time_out=True,
        params={"asset_cfg": SceneEntityCfg("robot")},
    )
    crab_failure = DoneTerm(
        func=terminate_crab_hex_failure,
        time_out=False,
        params={
            "asset_cfg": SceneEntityCfg("robot"),
            "limit_angle": 0.5,
            "minimum_root_height_z": None,
            "contact_force_threshold": 500.0,
            "hip_contact_sensor_cfg": SceneEntityCfg("contact_forces", body_names=[".*_Hip"]),
        },
    )


@configclass
class CrabHexStudentRewardsCfg:
    """Same pattern as Go2 ``StudentRewardsCfg``: collision term weight 0; hex collision bodies on ``contact_forces``."""

    reward_collision = RewTerm(
        func=mdp_rewards.reward_collision,
        weight=-0.0,
        params={
            "sensor_cfg": SceneEntityCfg(
                "contact_forces",
                body_names=["body", ".*_Hip", ".*_Femur"],
            ),
        },
    )


@configclass
class CrabHexTerminationsCfg:
    """Parkour episode term (timeout / goal / legacy fall) plus crab-specific early failure.

    Tune ``crab_failure.params``: ``limit_angle``, ``contact_force_threshold``, optional
    ``minimum_root_height_z``, ``hip_contact_sensor_cfg``. Env: ``KRABBY_HEX_TEACHER_MODE`` / spawn documented in scene/env cfgs.
    """

    total_terminates = DoneTerm(
        func=parkour_terminations.terminate_episode,
        time_out=True,
        params={"asset_cfg": SceneEntityCfg("robot")},
    )
    crab_failure = DoneTerm(
        func=terminate_crab_hex_failure,
        time_out=False,
        params={
            "asset_cfg": SceneEntityCfg("robot"),
            "limit_angle": 1.5,
            "minimum_root_height_z": None,
            "contact_force_threshold": 500.0,
            # Hips only: chassis ``body`` contact was ending episodes during benign brushes.
            "hip_contact_sensor_cfg": SceneEntityCfg("contact_forces", body_names=[".*_Hip"]),
        },
    )
