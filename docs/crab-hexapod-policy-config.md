# Crab hexapod — policy configuration (parkour / Isaac Lab)

This document describes **crab hexapod** policy, scene, and training configuration in **krabby-research**: file layout, observation/action/depth behavior, environment variables, and how to run tests and short training. Design write-ups elsewhere may use different dimensions or pseudocode; **this file matches the code in this repository.**

## Scope

- **Six legs:** Six foot bodies via `.*_Tibia`; **18** actuated actions (6 legs × 3 joints per leg).
- **PPO / policy:** Teacher and student gym ids, RSL-RL runner, `PPOWithExtractor` + `ActorCriticRMA`.
- **Depth:** Student scene uses the shared parkour ray-caster camera pattern, aligned with `parkour_tasks/default_cfg.py` (`CAMERA_CFG`).
- **Asset:** `assets/crab_hex.usd` (from `assets/crab_hex.usda`). Optional env override: `KRABBY_HEX_USD_PATH`.

## Config layout

| Area | Path |
|------|------|
| Scene (teacher / student) | `parkour/parkour_tasks/parkour_tasks/crab_hex_forward_task/config/crab_hex/crab_hex_scene_cfg.py` |
| Environment | `parkour/parkour_tasks/parkour_tasks/crab_hex_forward_task/config/crab_hex/crab_hex_env_cfg.py` |
| MDP (obs, actions, rewards) | `parkour/parkour_tasks/parkour_tasks/crab_hex_forward_task/config/crab_hex/agents/parkour_mdp_cfg.py` |
| PPO / runner | `parkour/parkour_tasks/parkour_tasks/crab_hex_forward_task/config/crab_hex/agents/rsl_rl_ppo_cfg.py` |
| Gym registration | `parkour/parkour_tasks/parkour_tasks/crab_hex_forward_task/config/crab_hex/__init__.py` |
| Integration tests | `tests/integration/test_crab_hexapod_policy_config.py` |

## Observation and action

- **Policy observation:** Single term `extreme_parkour_observations` (`ExtremeParkourObservations`) in `CrabHexTeacherObservationsCfg` / student policy cfg. Reference run: **1251** dimensions for the `policy` group (with default history settings).
- **Actions:** `DelayedJointPositionActionCfg` on:
  - `.*_HipMount_HipRevoluteJoint`
  - `.*_Hip_FemurPrismatic_PrismaticJoint`
  - `.*_Femur_TibiaPrismatic_PrismaticJoint`  
  → **18** dimensions.
- **Critic / privileged:** Inherited parkour teacher pattern (same family as Go2 teacher).

## Depth camera

- **Student:** `CrabHexStudentSceneCfg` sets  
  `depth_camera = CAMERA_CFG.replace(prim_path="{ENV_REGEX_NS}/Robot/KrabbyUno/base_link/depth_camera")`.
- **`CAMERA_CFG`:** `RayCasterCameraCfg`, `distance_to_camera`, pattern **height=60, width=106**, offset/orientation shared with the parkour stack (`parkour_tasks/default_cfg.py`).
- **USD:** `KrabbyUno/base_link/depth_camera` hierarchy in `assets/crab_hex.usda`.

## Rewards (hex naming)

- Base / collision bodies: `Plate_Bottom`, `.*_Tibia`, `.*_Femur` as configured in `CrabHexRewardsCfg`.
- Feet / edge / stumble: `.*_Tibia`.
- Hip posture: `.*_HipMount_HipRevoluteJoint`.

## Gait tuning (where to look)

- Commands: `CommandsCfg` / `base_velocity`.
- Rewards: `CrabHexRewardsCfg`.
- Terrain / curriculum: inherited teacher/student env configs.

## Isaac Sim 5.x / rsl_rl notes

- **`PPOWithExtractor`:** Standalone trainer using `RolloutStorage` with `TensorDict` keys `policy` and `critic` (not a subclass of stock `rsl_rl.PPO`).
- **`OnPolicyRunnerWithExtractor`:** `add_git_repo_to_log` → `git_status_repos`; `store_code_state` optional with one-time warning; `multi_gpu_cfg` from `cfg["multi_gpu"]`; `process_env_step` takes post-step `TensorDict`.
- Extra algorithm keys (e.g. `share_cnn_encoders`) may be filtered with a warning.

## Environment variables

| Variable | Purpose |
|----------|---------|
| `PYTHONPATH` | Must include **`parkour/parkour_tasks`** (directory containing the `parkour_tasks` package) for imports when using `isaaclab.sh -p`. |
| `KRABBY_HEX_USD_PATH` | Absolute path to the hexapod stage (`crab_hex.usd` or **`crab_hex.usda`**). **Use the same path for GUI and headless runs** (`echo "$KRABBY_HEX_USD_PATH"` before launch). Prefer pointing at **`assets/crab_hex.usda`** while iterating so PhysX sees edits without re-export; for deployment, use a binary `.usd` exported from that usda (Omniverse: open usda → Export, or your pipeline’s `usdcat`/`usdconvert`). A stale `.usd` that predates friction fixes can trigger PhysX joint friction errors. |
| `RUN_CRAB_HEX_RUNTIME_SMOKE` | Set to `1` to enable Isaac env rollout tests in pytest. |
| `KRABBY_PHASE` | **Training-phase preset** (`1a`, `2a`, `2b`, `2c`, `3a`, `3b`; `legacy_golden_1a…2e`). Expands into the `KRABBY_*` knobs of the baked curriculum with *setdefault* semantics (an explicitly exported variable wins), including `KRABBY_HEX_TEACHER_MODE` for phase 2. Defined in `config/crab_hex/crab_hex_phases.py`; applied on import of the crab-hex config package. |
| `KRABBY_PLANT` | Plant (morphology) preset: `golden`, `B`, `A10`, `A15`, `A20`, `A10+B`, `A15+B`, `A20+B` → sets `KRABBY_HEX_USD_PATH` to the generated variant. |
| `KRABBY_STUDENT_MDP` | `1` makes `Isaac-Crab-Hex-Student-v0` use the phase-3 structure (2c teacher terrain generator, flat-walk terminations, `full` actions, DR on the chassis) without a phase preset — for evaluating a phase-3 student with explicit knobs. |
| `KRABBY_HEX_TEACHER_MODE` | Teacher MDP mode: `2a`/`2b`/`2c` (paradigm phase 2 = flat-walk MDP + elements) or the legacy `bridge`/`2b1`/`2b2`/`full1`/`full2`/`full`. The flat-walk task ignores it. |
| other `KRABBY_*` | Expert overrides of individual knobs (element weights, terrain presets, DR, RSI, exposure, `KRABBY_PHASEOUT` ramps). Prefer `KRABBY_PHASE`; see `crab_hex_phases.py` for the recorded stacks. |

## Commands

From **`krabby-research/parkour`**:

```bash
export PYTHONPATH="$(pwd)/parkour_tasks:${PYTHONPATH}"
export KRABBY_HEX_USD_PATH="/absolute/path/to/krabby-research/assets/crab_hex.usd"

# Tests (from krabby-research root; runtime smokes skip unless RUN_CRAB_HEX_RUNTIME_SMOKE=1)
cd /absolute/path/to/krabby-research
/path/to/IsaacLab/isaaclab.sh -p -m pytest tests/integration/test_crab_hexapod_policy_config.py -v
RUN_CRAB_HEX_RUNTIME_SMOKE=1 /path/to/IsaacLab/isaaclab.sh -p -m pytest tests/integration/test_crab_hexapod_policy_config.py -v

# Paradigm phases (current): one preset per phase, plant by name
KRABBY_PHASE=1a KRABBY_PLANT=A15+B python scripts/rsl_rl/train.py --task Isaac-Crab-Hex-Flat-Walk-v0 --headless --num_envs 256 --seed 3 --max_iterations 5000
KRABBY_PHASE=2a KRABBY_PLANT=A15+B python scripts/rsl_rl/train.py --task Isaac-Crab-Hex-Teacher-v0 --headless --num_envs 256 --seed 3 --max_iterations 5000 --resume --checkpoint <1a head>
KRABBY_PHASE=3a KRABBY_PLANT=A15+B python scripts/rsl_rl/train.py --task Isaac-Crab-Hex-Student-v0 --headless --num_envs 192 --seed 3 --max_iterations 5000 --resume --checkpoint <2c head>
# Config identity of the presets (6 headless boots, no sim stepping)
RUN_CRAB_HEX_CFG_IDENTITY=1 python -m pytest tests/integration/test_crab_hex_phase_configs.py -v

# Short teacher training
cd /absolute/path/to/krabby-research/parkour
/path/to/IsaacLab/isaaclab.sh -p scripts/rsl_rl/train.py \
  --task Isaac-Crab-Hex-Teacher-v0 --headless --num_envs 4 --max_iterations 5
```

Registered tasks: **`Isaac-Crab-Hex-Teacher-v0`**, **`Isaac-Crab-Hex-Student-v0`**.
