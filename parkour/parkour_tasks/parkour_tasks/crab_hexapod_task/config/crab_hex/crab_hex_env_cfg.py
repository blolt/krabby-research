import os

from isaaclab.envs import ViewerCfg
from isaaclab.managers import SceneEntityCfg
from isaaclab.utils import configclass

from parkour_tasks.crab_hexapod_task.config.crab_hex.agents.parkour_mdp_cfg import (
    CommandsCfg,
    CrabHexFlatWalkActionsCfg,
    CrabHexFlatWalkRewardsCfg,
    CrabHexFlatWalkTerminationsCfg,
    CrabHexRewardsCfg,
    CrabHexTeacherObservationsCfg,
    CrabHexStage2BPhase1RewardsCfg,
    CrabHexStage2BPhase2RewardsCfg,
    CrabHexTeacherBridgeRewardsCfg,
    CrabHexTerminationsCfg,
    EventCfg,
    ParkourEventsCfg,
)
from parkour_tasks.crab_hexapod_task.config.crab_hex.crab_hex_scene_cfg import CrabHexTeacherSceneCfg
from parkour_tasks.crab_hexapod_task.config.crab_hex.crab_hex_student_cfg import (
    CrabHexStudentParkourEnvCfg,
)
from parkour_tasks.extreme_parkour_task.config.go2.parkour_teacher_cfg import (
    UnitreeGo2TeacherParkourEnvCfg,
)

# Front 3/4 view: FL/FR at −x; Go2 ``VIEWER`` is a tight +y side shot.
CRAB_HEX_VIEWER = ViewerCfg(
    eye=(-4.0, 0.5, 1.55),
    lookat=(0.0, 0.0, 0.35),
    asset_name="robot",
    origin_type="asset_root",
)
# Top view: directly above root (raise z for wider view)
# CRAB_HEX_VIEWER = ViewerCfg(
#     eye=(0.0, 0.0, 6.0),      # directly above root (raise z for wider view)
#     lookat=(0.0, 0.0, 0.35),  # same as now — chassis height
#     asset_name="robot",
#     origin_type="asset_root",
# )

# ---------------------------------------------------------------------------
# ``KRABBY_HEX_TEACHER_MODE`` — teacher curriculum (``Isaac-Crab-Hex-Teacher-v0``)
#
# Set before train/play:  export KRABBY_HEX_TEACHER_MODE=<mode>
# Unset or omit for:     default full parkour teacher (``full``).
#
# Pipeline (checkpoint chain):
#   Stage 1  Flat walk     →  task ``Isaac-Crab-Hex-Flat-Walk-v0`` (NOT this flag)
#   Stage 2a bridge        →  ``bridge``   resume flat ``model_6000``
#   Stage 2b phase 1       →  ``2b1``      resume bridge ``model_6099``
#   Stage 2b phase 2       →  ``2b2``      teacher-ready obstacle walk (distillation source)
#   Stage 3  Student       →  ``Isaac-Crab-Hex-Student-v0``  distill from 2b2 teacher
#   Stage 4  Full parkour  →  ``full``     TODO — only after 2b2 student pipeline is stable
#
# --- bridge (Appendix D) — “easy mixed walk” ---
#   Intent: Keep the flat-walk gait on mostly flat ground with a little shallow
#   parkour geometry; learn velocity + posture, not goal chasing yet.
#   Terrain: ~82% flat tiles, ~18% shallow gaps/pits; difficulty 0.08–0.30;
#            terrain level frozen (no curriculum demotion).
#   Actions: scale 0.24, clip ±1 (same family as flat-walk).
#   Rewards: ``CrabHexTeacherBridgeRewardsCfg`` — forward speed/progress, upright,
#            anti-stall; parkour goal/yaw terms OFF.
#   Typical play: stable forward walk on flat + light tiles; some heading drift OK.
#
# --- 2b1 — “hybrid walk + light parkour hints” ---
#   Intent: Same bridge-lite physics/terrain as ``bridge``, but gently introduce
#   parkour goal velocity and yaw (aux weights) plus teacher body regularizers.
#   Terrain/actions/events: same as ``bridge``.
#   Rewards: ``CrabHexStage2BPhase1RewardsCfg`` — bridge core + goal_vel 0.75, yaw 0.2.
#   Resume: always from bridge ``model_6099`` (do not use ``full`` from 6099).
#
# --- 2b2 — “teacher-ready obstacle walk” ---
#   Intent: Polished 2b2-phase-2 policy for **student distillation** (robustness over raw speed).
#   Terrain: 50/50 flat/parkour; curriculum 0.20–0.70; moderate geometry; actions 0.24, ±1.
#   Rewards: ``CrabHexStage2BPhase2RewardsCfg`` — clearance **+1.8**, foot **+2.0**, swing-vz **+0.4**;
#            recover **+0.4**, micro-swing **−0.2**, forward **+0.25**, low-speed **−0.8**.
#   Stop at sweet-spot checkpoint (play + metric gates); bundle as 2b2-teacher before student train.
#   Bundled teacher: Appendix F ``2026-05-26_21-46-37/model_6300.pt`` (supersedes ``2026-05-26_11-30-18``).
#
# --- full (TODO stage 4) — “Go2-style parkour teacher” ---
#   Intent: Full extreme-parkour teacher MDP (goal velocity primary).
#   Terrain: full sub-terrain mix, difficulty 0.0–1.0, curriculum on.
#   Actions: scale 0.25, clip ±4.8; push/mass/COM domain randomization on.
#   Rewards: ``CrabHexRewardsCfg`` (goal_vel 2.25, collision -6, …).
#   Warning: resuming bridge/2b1 checkpoints into ``full`` without staging thrashes.
#
# Play must use the same ``KRABBY_HEX_TEACHER_MODE`` as training for that checkpoint.
# ---------------------------------------------------------------------------


def _crab_hex_teacher_mode() -> str:
    """Resolve ``KRABBY_HEX_TEACHER_MODE`` → ``bridge`` | ``2b1`` | ``2b2`` | ``full1`` | ``full2`` |
    ``full`` (see module comment above).

    ``full1``/``full2`` are intermediate ramp stages between 2b2 and true ``full`` -- jumping
    straight from 2b2's bridge-lite MDP to full's (terrain 0-1, full domain randomization,
    0.25/±4.8 actions, strict 500N failure threshold) all at once collapses training almost
    immediately (verified empirically: crab_failure pinned at 100% within ~50 iterations, never
    recovering). Each ramp stage narrows the gap on every axis at once by a smaller amount.
    """
    raw = os.environ.get("KRABBY_HEX_TEACHER_MODE", "").strip().lower()
    if raw in ("bridge",):
        return "bridge"
    if raw in ("2b1", "2b_1", "stage2b1", "stage2b-1", "stage2b_1"):
        return "2b1"
    if raw in ("2b2", "2b_2", "stage2b2", "stage2b-2", "stage2b_2"):
        return "2b2"
    if raw in ("full1", "full_1", "full-1", "fullramp1", "full-ramp-1"):
        return "full1"
    if raw in ("full2", "full_2", "full-2", "fullramp2", "full-ramp-2"):
        return "full2"
    return "full"


def _crab_hex_bridge_like_mdp_active() -> bool:
    """Train/play uses bridge-lite physics (scale 0.24, ±1), not default teacher 0.25 / ±4.8."""
    return _crab_hex_teacher_mode() in ("bridge", "2b1", "2b2")


def _apply_crab_hex_stage_2b_bridge_lite_env(cfg, *, action_scale: float = 0.24) -> None:
    """Shared bridge-lite physics/events/terminations for stage-2b (phase 1 and 2)."""
    _apply_crab_hex_bridge_actions_and_events(cfg, action_scale=action_scale)
    cfg.commands.base_velocity.ranges.heading = (0.0, 0.0)
    cfg.commands.base_velocity.heading_control_stiffness = 1.5
    cfg.commands.base_velocity.ranges.lin_vel_x = (0.45, 0.85)


def _apply_crab_hex_stage_2b_phase1_terrain(cfg) -> None:
    """Bridge-equivalent terrain: frozen levels, easy mix, shallow gaps."""
    cfg.parkours.base_parkour.freeze_terrain_levels = True
    tg = getattr(cfg.scene.terrain, "terrain_generator", None) if cfg.scene.terrain else None
    if tg is not None:
        _apply_crab_hex_easy_mixed_terrain(tg, flat_proportion=0.825, difficulty_range=(0.08, 0.30))
        _apply_crab_hex_bridge_shallow_parkour_geometry(tg)


def _apply_crab_hex_stage_2b_phase2_parkour_geometry(tg) -> None:
    """Moderate parkour geometry for 2b2 (between bridge-shallow and full teacher)."""
    if "parkour_gap" in tg.sub_terrains:
        gap = tg.sub_terrains["parkour_gap"]
        gap.gap_depth = (0.08, 0.18)
        gap.gap_size = "0.10 + 0.45 * difficulty"
        gap.half_valid_width = (0.85, 1.15)
    if "parkour" in tg.sub_terrains:
        stone = tg.sub_terrains["parkour"]
        stone.pit_depth = (0.08, 0.18)
        stone.incline_height = "0.20*difficulty"
        stone.last_incline_height = "incline_height + 0.08 - 0.06*difficulty"
    if "parkour_step" in tg.sub_terrains:
        tg.sub_terrains["parkour_step"].step_height = "0.12 + 0.28*difficulty"
    if "parkour_hurdle" in tg.sub_terrains:
        tg.sub_terrains["parkour_hurdle"].hurdle_height_range = (
            "0.12+0.10*difficulty, 0.16+0.20*difficulty"
        )


def _apply_crab_hex_stage_2b_phase2_terrain(cfg) -> None:
    """Phase 2: curriculum on, 50/50 mix, gently ramping obstacle difficulty."""
    cfg.parkours.base_parkour.freeze_terrain_levels = False
    tg = getattr(cfg.scene.terrain, "terrain_generator", None) if cfg.scene.terrain else None
    if tg is not None:
        tg.curriculum = True
        tg.difficulty_range = (0.20, 0.70)
        active = [k for k in tg.sub_terrains if k not in ("parkour_flat", "parkour_demo")]
        n_other = len(active)
        share = (0.5 / n_other) if n_other else 0.0
        for key, sub_terrain in tg.sub_terrains.items():
            if key == "parkour_flat":
                sub_terrain.proportion = 0.5
            elif key == "parkour_demo":
                sub_terrain.proportion = 0.0
            else:
                sub_terrain.proportion = share
            sub_terrain.noise_range = (0.02, 0.02)
        _apply_crab_hex_stage_2b_phase2_parkour_geometry(tg)


def _apply_crab_hex_student_2b2_teacher_mdp(cfg) -> None:
    """Student distillation MDP aligned with ``KRABBY_HEX_TEACHER_MODE=2b2`` teacher train.

    Same terrain mix, difficulty, geometry, commands, and bridge-lite DR as 2b2 teacher.
    Keeps student action delay (``use_delay=True``) — not overwritten by bridge-lite actions.
    """
    _apply_crab_hex_stage_2b_phase2_terrain(cfg)
    cfg.commands.base_velocity.ranges.heading = (0.0, 0.0)
    cfg.commands.base_velocity.heading_control_stiffness = 1.5
    cfg.commands.base_velocity.ranges.lin_vel_x = (0.45, 0.85)
    cfg.events.push_by_setting_velocity = None
    cfg.events.randomize_rigid_body_mass = None
    cfg.events.randomize_rigid_body_com = None
    cfg.terminations.crab_failure.params["contact_force_threshold"] = 800.0
    tg = getattr(cfg.scene.terrain, "terrain_generator", None) if cfg.scene.terrain else None
    if tg is not None:
        tg.horizontal_scale = 0.08
        for sub_terrain in tg.sub_terrains.values():
            sub_terrain.horizontal_scale = 0.08
            sub_terrain.use_simplified = False


def _apply_crab_hex_bridge_actions_and_events(cfg, *, action_scale: float = 0.24) -> None:
    """Flat-walk-compatible actions/events for the flat-walk → teacher bridge."""
    cfg.actions.joint_pos.scale = action_scale
    cfg.actions.joint_pos.clip = {".*": (-1.0, 1.0)}
    cfg.actions.joint_pos.use_delay = False
    cfg.actions.joint_pos.history_length = 1

    cfg.events.push_by_setting_velocity = None
    cfg.events.randomize_rigid_body_mass = None
    cfg.events.randomize_rigid_body_com = None

    cfg.terminations.crab_failure.params["contact_force_threshold"] = 800.0


def _apply_crab_hex_full_actions(cfg) -> None:
    """Stage 4 (``full``): restore 0.25 scale / ±4.8 raw clip, action delay on -- matches the
    original Go2-imported ``ActionsCfg`` this repo used before the cam-mechanism migration
    (stages 1-2b2 override down to a softer 0.24/±1, see ``_apply_crab_hex_bridge_actions_and_events``).
    ``cfg.actions.joint_pos.joint_names`` itself is unaffected -- already fixed at the class-level
    default (``CrabHexFlatWalkActionsCfg``) to exclude the passive ``*_Body_Hip_RevoluteJoint``.
    """
    cfg.actions.joint_pos.scale = 0.25
    cfg.actions.joint_pos.clip = {".*": (-4.8, 4.8)}
    cfg.actions.joint_pos.use_delay = True
    cfg.actions.joint_pos.history_length = 8


def _apply_crab_hex_full_ramp1_actions(cfg) -> None:
    """full-ramp-1: 0.245 scale / ±2.4 clip -- midpoint between 2b2-lite (0.24/±1) and true full
    (0.25/±4.8), so the policy adapts to a larger raw action range gradually instead of in one jump.
    """
    cfg.actions.joint_pos.scale = 0.245
    cfg.actions.joint_pos.clip = {".*": (-2.4, 2.4)}
    cfg.actions.joint_pos.use_delay = True
    cfg.actions.joint_pos.history_length = 8


def _apply_crab_hex_full_ramp2_actions(cfg) -> None:
    """full-ramp-2: 0.25 scale / ±3.6 clip -- most of the way to true full's ±4.8."""
    cfg.actions.joint_pos.scale = 0.25
    cfg.actions.joint_pos.clip = {".*": (-3.6, 3.6)}
    cfg.actions.joint_pos.use_delay = True
    cfg.actions.joint_pos.history_length = 8


def _apply_crab_hex_full_ramp1_dr(cfg) -> None:
    """Half-strength push/mass/com domain randomization (vs. Go2's original EventCfg ranges --
    see push_by_setting_velocity/randomize_rigid_body_mass/randomize_rigid_body_com in
    extreme_parkour_task/config/go2/parkour_mdp_cfg.py) -- 2b2 disables these entirely, true full
    uses them at 100%; ramp1 uses half so the jump isn't instant.
    """
    if cfg.events.push_by_setting_velocity is not None:
        cfg.events.push_by_setting_velocity.params["velocity_range"] = {"x": (-0.25, 0.25), "y": (-0.25, 0.25)}
    if cfg.events.randomize_rigid_body_mass is not None:
        cfg.events.randomize_rigid_body_mass.params["mass_distribution_params"] = (-0.5, 1.5)
    if cfg.events.randomize_rigid_body_com is not None:
        cfg.events.randomize_rigid_body_com.params["com_range"] = {"x": (-0.01, 0.01), "y": (-0.01, 0.01), "z": (-0.01, 0.01)}


def _apply_crab_hex_full_ramp1_terrain(cfg) -> None:
    """full-ramp-1: curriculum on, difficulty (0.15, 0.60), 40% flat, gentle 2b2-style obstacle
    geometry (not yet raw Go2 formulas) -- a smaller step up from 2b2's own (0.20, 0.70) mix.
    """
    cfg.parkours.base_parkour.freeze_terrain_levels = False
    tg = getattr(cfg.scene.terrain, "terrain_generator", None) if cfg.scene.terrain else None
    if tg is not None:
        tg.curriculum = True
        tg.difficulty_range = (0.15, 0.60)
        active = [k for k in tg.sub_terrains if k not in ("parkour_flat", "parkour_demo")]
        n_other = len(active)
        share = (0.60 / n_other) if n_other else 0.0
        for key, sub_terrain in tg.sub_terrains.items():
            if key == "parkour_flat":
                sub_terrain.proportion = 0.40
            elif key == "parkour_demo":
                sub_terrain.proportion = 0.0
            else:
                sub_terrain.proportion = share
        _apply_crab_hex_stage_2b_phase2_parkour_geometry(tg)


def _apply_crab_hex_full_ramp2_terrain(cfg) -> None:
    """full-ramp-2: curriculum on, difficulty (0.05, 0.90), 15% flat, raw (unmodified) Go2
    ``EXTREME_PARKOUR_TERRAINS_CFG`` obstacle geometry -- the last step before true full's (0, 1).
    """
    cfg.parkours.base_parkour.freeze_terrain_levels = False
    tg = getattr(cfg.scene.terrain, "terrain_generator", None) if cfg.scene.terrain else None
    if tg is not None:
        tg.curriculum = True
        tg.difficulty_range = (0.05, 0.90)
        active = [k for k in tg.sub_terrains if k not in ("parkour_flat", "parkour_demo")]
        n_other = len(active)
        share = (0.85 / n_other) if n_other else 0.0
        for key, sub_terrain in tg.sub_terrains.items():
            if key == "parkour_flat":
                sub_terrain.proportion = 0.15
            elif key == "parkour_demo":
                sub_terrain.proportion = 0.0
            else:
                sub_terrain.proportion = share


def _apply_crab_hex_easy_mixed_terrain(
    tg, *, flat_proportion: float, difficulty_range: tuple[float, float]
) -> None:
    """``parkour_flat`` + easy parkour sub-terrains (e.g. 50/50 or 70/30)."""
    tg.curriculum = False
    tg.difficulty_range = difficulty_range
    active = [k for k in tg.sub_terrains if k not in ("parkour_flat", "parkour_demo")]
    n_other = len(active)
    share = ((1.0 - flat_proportion) / n_other) if n_other else 0.0
    for key, sub_terrain in tg.sub_terrains.items():
        if key == "parkour_flat":
            sub_terrain.proportion = flat_proportion
        elif key == "parkour_demo":
            sub_terrain.proportion = 0.0
        else:
            sub_terrain.proportion = share
        sub_terrain.noise_range = (0.02, 0.02)


def _apply_crab_hex_bridge_shallow_parkour_geometry(tg) -> None:
    """Shallow, narrow gaps/pits for bridge (depth is not scaled by ``difficulty_range``)."""
    if "parkour_gap" in tg.sub_terrains:
        gap = tg.sub_terrains["parkour_gap"]
        gap.gap_depth = (0.05, 0.12)
        gap.gap_size = "0.08 + 0.35 * difficulty"
        gap.half_valid_width = (0.9, 1.2)
    if "parkour" in tg.sub_terrains:
        tg.sub_terrains["parkour"].pit_depth = (0.05, 0.12)


@configclass
class CrabHexTeacherEnvCfg(UnitreeGo2TeacherParkourEnvCfg):
    viewer = CRAB_HEX_VIEWER
    scene: CrabHexTeacherSceneCfg = CrabHexTeacherSceneCfg(num_envs=6144, env_spacing=1.0)
    observations: CrabHexTeacherObservationsCfg = CrabHexTeacherObservationsCfg()
    # NOTE(cam-mechanism-migration): reuses CrabHexFlatWalkActionsCfg (not the Go2-imported
    # ``ActionsCfg``) -- the cam-shaft joints replace ``Body_Hip`` as the driven yaw DOF, so the
    # action space must exclude the now-passive ``Body_Hip`` joints the same way flat-walk's does.
    # Also required for checkpoint-shape compatibility when resuming Stage 2a from the flat-walk
    # checkpoint (both must have the same 18-dim action space).
    actions: CrabHexFlatWalkActionsCfg = CrabHexFlatWalkActionsCfg()
    commands: CommandsCfg = CommandsCfg()
    rewards: CrabHexRewardsCfg = CrabHexRewardsCfg()
    terminations: CrabHexTerminationsCfg = CrabHexTerminationsCfg()
    parkours: ParkourEventsCfg = ParkourEventsCfg()
    events: EventCfg = EventCfg()

    def __post_init__(self):
        super().__post_init__()
        self.sim.physx.enable_external_forces_every_iteration = True
        # Skew velocity commands toward meaningful forward speed (reduces near-zero command_vel in rewards).
        self.commands.base_velocity.ranges.lin_vel_x = (0.45, 0.85)
        base_body_cfg = SceneEntityCfg("robot", body_names="body")
        if self.events.base_external_force_torque is not None:
            self.events.base_external_force_torque.params["asset_cfg"] = base_body_cfg
        if self.events.randomize_rigid_body_mass is not None:
            self.events.randomize_rigid_body_mass.params["asset_cfg"] = base_body_cfg
        if self.events.randomize_rigid_body_com is not None:
            self.events.randomize_rigid_body_com.params["asset_cfg"] = base_body_cfg

        mode = _crab_hex_teacher_mode()
        if mode == "bridge":
            _apply_crab_hex_stage_2b_bridge_lite_env(self)
            self.rewards = CrabHexTeacherBridgeRewardsCfg()
            _apply_crab_hex_stage_2b_phase1_terrain(self)
        elif mode == "2b1":
            _apply_crab_hex_stage_2b_bridge_lite_env(self)
            self.rewards = CrabHexStage2BPhase1RewardsCfg()
            _apply_crab_hex_stage_2b_phase1_terrain(self)
        elif mode == "2b2":
            _apply_crab_hex_stage_2b_bridge_lite_env(self)
            self.rewards = CrabHexStage2BPhase2RewardsCfg()
            _apply_crab_hex_stage_2b_phase2_terrain(self)
        elif mode == "full1":
            # Ramp stage 1/2 toward full (see _crab_hex_teacher_mode docstring): eases actions,
            # DR, terrain, and the failure threshold partway from 2b2's bridge-lite MDP toward
            # true full, instead of jumping all four axes to their hardest values simultaneously.
            _apply_crab_hex_full_ramp1_actions(self)
            _apply_crab_hex_full_ramp1_dr(self)
            _apply_crab_hex_full_ramp1_terrain(self)
            self.terminations.crab_failure.params["contact_force_threshold"] = 750.0
        elif mode == "full2":
            # Ramp stage 2/2: DR left at class-level EventCfg defaults (full strength) --
            # only full1 needs the half-strength override.
            _apply_crab_hex_full_ramp2_actions(self)
            _apply_crab_hex_full_ramp2_terrain(self)
            self.terminations.crab_failure.params["contact_force_threshold"] = 600.0
        else:
            # mode == "full": rewards (CrabHexRewardsCfg) and terrain (full Go2 sub-terrain mix,
            # difficulty 0-1, domain randomization on) stay at their class-level defaults --
            # only actions need restoring to 0.25/±4.8 (see _apply_crab_hex_full_actions docstring).
            _apply_crab_hex_full_actions(self)


@configclass
class CrabHexFlatWalkEnvCfg(CrabHexTeacherEnvCfg):
    """Stage 1 **gait** (``Isaac-Crab-Hex-Flat-Walk-v0``): no ``KRABBY_HEX_TEACHER_MODE``.

    Learn alternating hex footfall on 100% flat tiles before any teacher mode.
    Rewards emphasize commanded speed, forward progress, upright pose, and light
    swing/stance shaping — not parkour goals. See README §3.0 and
    ``CrabHexFlatWalkRewardsCfg``.
    """

    actions: CrabHexFlatWalkActionsCfg = CrabHexFlatWalkActionsCfg()
    rewards: CrabHexFlatWalkRewardsCfg = CrabHexFlatWalkRewardsCfg()
    terminations: CrabHexFlatWalkTerminationsCfg = CrabHexFlatWalkTerminationsCfg()

    def __post_init__(self):
        super().__post_init__()
        # Straight flat-walk: fixed world heading 0; P-control corrects slow yaw drift in play/train.
        self.commands.base_velocity.ranges.lin_vel_x = (0.30, 0.65)
        self.commands.base_velocity.ranges.heading = (0.0, 0.0)
        self.commands.base_velocity.heading_control_stiffness = 1.5
        self.events.push_by_setting_velocity = None
        self.events.randomize_rigid_body_mass = None
        self.events.randomize_rigid_body_com = None
        tg = getattr(self.scene.terrain, "terrain_generator", None) if self.scene.terrain else None
        if tg is not None:
            tg.curriculum = False
            tg.difficulty_range = (0.1, 0.25)
            for key, sub_terrain in tg.sub_terrains.items():
                if key == "parkour_flat":
                    sub_terrain.proportion = 1.0
                else:
                    sub_terrain.proportion = 0.0


@configclass
class CrabHexFlatWalkEnvCfgPLAY(CrabHexFlatWalkEnvCfg):
    """Flat-walk visualization: follow-cam and command debug."""

    viewer = CRAB_HEX_VIEWER

    def __post_init__(self):
        super().__post_init__()
        self.episode_length_s = 60.0
        self.parkours.base_parkour.debug_vis = True
        self.commands.base_velocity.debug_vis = True
        if self.scene.terrain is not None:
            self.scene.terrain.max_init_terrain_level = None


@configclass
class CrabHexTeacherEnvCfgPLAY(CrabHexTeacherEnvCfg):
    """Visualization / evaluation: follow-cam, parkour debug, longer episodes, structured parkour mix.

    **Default terrain is the easy / flat-heavy mix** so stance checks are not confused with hard parkour.
    Set ``KRABBY_HEX_PLAY_HARD=1`` for the previous high-difficulty play preset (no flat, 0.7–1.0 difficulty).
    """

    viewer = CRAB_HEX_VIEWER

    def __post_init__(self):
        super().__post_init__()
        self.episode_length_s = 60.0
        self.parkours.base_parkour.debug_vis = True
        self.commands.base_velocity.debug_vis = True
        if self.scene.terrain is not None:
            self.scene.terrain.max_init_terrain_level = None
        # Bridge / stage-2b train sets terrain in ``CrabHexTeacherEnvCfg``; play must match train.
        if _crab_hex_bridge_like_mdp_active():
            return
        tg = getattr(self.scene.terrain, "terrain_generator", None) if self.scene.terrain else None
        if tg is not None:
            play_easy_flag = os.environ.get("KRABBY_HEX_PLAY_EASY", "").strip().lower() in ("1", "true", "yes")
            play_hard_flag = os.environ.get("KRABBY_HEX_PLAY_HARD", "").strip().lower() in ("1", "true", "yes")
            # Default easy unless explicitly requesting hard parkour (legacy was hard unless PLAY_EASY).
            easy = play_easy_flag or not play_hard_flag
            if easy:
                tg.difficulty_range = (0.15, 0.55)
                active = [
                    k
                    for k in tg.sub_terrains
                    if k not in ("parkour_flat", "parkour_demo")
                ]
                n_other = len(active)
                share = (0.5 / n_other) if n_other else 0.0
                for key, sub_terrain in tg.sub_terrains.items():
                    if key == "parkour_flat":
                        sub_terrain.proportion = 0.5
                    elif key == "parkour_demo":
                        sub_terrain.proportion = 0.0
                    else:
                        sub_terrain.proportion = share
                    sub_terrain.noise_range = (0.02, 0.02)
            else:
                tg.difficulty_range = (0.7, 1.0)
                for key, sub_terrain in tg.sub_terrains.items():
                    if key == "parkour_flat":
                        sub_terrain.proportion = 0.0
                    else:
                        sub_terrain.proportion = 0.2
                        sub_terrain.noise_range = (0.02, 0.02)


@configclass
class CrabHexStudentEnvCfg(CrabHexStudentParkourEnvCfg):
    """Gym entry ``Isaac-Crab-Hex-Student-v0``: depth student MDP matched to 2b2 teacher terrain."""

    def __post_init__(self):
        super().__post_init__()
        _apply_crab_hex_student_2b2_teacher_mdp(self)
        base_body_cfg = SceneEntityCfg("robot", body_names="body")
        if self.events.base_external_force_torque is not None:
            self.events.base_external_force_torque.params["asset_cfg"] = base_body_cfg


@configclass
class CrabHexStudentEnvCfgPLAY(CrabHexStudentEnvCfg):
    """Visualization: ``CRAB_HEX_VIEWER`` follow-cam (same as ``CrabHexTeacherEnvCfgPLAY``).

    Set ``KRABBY_HEX_PLAY_FLAT=1`` for 100% flat tiles (student MDP / obs unchanged).
    """

    viewer = CRAB_HEX_VIEWER

    def __post_init__(self):
        super().__post_init__()
        self.episode_length_s = 60.0
        self.parkours.base_parkour.debug_vis = True
        self.commands.base_velocity.debug_vis = True
        if self.scene.terrain is not None:
            self.scene.terrain.max_init_terrain_level = None
        self.events.push_by_setting_velocity = None
        if os.environ.get("KRABBY_HEX_PLAY_FLAT", "").strip().lower() in ("1", "true", "yes"):
            self.parkours.base_parkour.freeze_terrain_levels = True
            tg = getattr(self.scene.terrain, "terrain_generator", None) if self.scene.terrain else None
            if tg is not None:
                tg.curriculum = False
                tg.difficulty_range = (0.1, 0.25)
                for key, sub_terrain in tg.sub_terrains.items():
                    if key == "parkour_flat":
                        sub_terrain.proportion = 1.0
                    else:
                        sub_terrain.proportion = 0.0
