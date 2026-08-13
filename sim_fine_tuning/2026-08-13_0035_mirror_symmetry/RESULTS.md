# Mirror-symmetry training campaign

Pre-authorized by user 2026-08-13 after the seed search (0/7 alternating, handedness broke both
directions). Goal: make permanent lead-set preference impossible to encode by enforcing the
robot's L/R mirror symmetry (which maps tripod set A={FL,MR,RL} exactly onto B={FR,ML,RR}).

## Implementation route (confirmed by code exploration)

`PPOWithExtractor` (parkour/scripts/rsl_rl/modules/ppo_with_extractor.py) ALREADY carries
rsl-rl's symmetry machinery: `symmetry_cfg` dict {use_data_augmentation, use_mirror_loss,
data_augmentation_func (resolvable path), mirror_loss_coeff}; mirror-loss path at lines
428-452: L_sym = MSE(policy_mean(mirror(obs)), mirror(policy_mean(obs))), added at coef.
We only supply the crab-specific `data_augmentation_func` + cfg wiring. Function contract:
`f(obs, actions, env, obs_type)` → (cat([obs; mirror(obs)]), cat([act; mirror(act)])), each
arg optionally None.

## Mirror-map specification (policy obs = 87 proprio + 132 scan + 9 priv_e + 53 priv_l + 870 history = 1151)

**Proprio (15 head dims)**: [0]wx→−, [1]wy→+, [2]wz→−, [3]roll→−, [4]pitch→+, [5]0·dy→−,
[6]delta_yaw→−, [7]delta_next_yaw→−, [8]0·cmd_vx→+, [9]0·cmd_vy→−, [10]cmd_vx→+, [11]env_idx→+,
[12]inv_idx→+, [13]lin_vx→+, [14]lin_vy→−. Then joint_pos−default (24), joint_vel×0.05 (24) —
joint map below; last action (18) — action map below; contact fill (6): swap FL↔FR, ML↔MR,
RL↔RR, sign +.

**Joint map (24 dims, articulation order resolved at runtime)**: L↔R pair swap per joint type
with signs: Body_CamShaft − (Whitworth map atan2(K sinθ, 1+K cosθ) verified ODD → defaults
negate L/R); Body_Hip (passive) −; Hip_Femur + (defaults equal L/R, 0.30); Femur_Tibia −
(180° Z USD flip convention). KNOWN APPROXIMATION: knee defaults are −0.07(L)/+0.10(R), not an
exact negation — the 0.03 rad deliberate roll-balance asymmetry makes the delta-mirror
approximate on knees (≤0.03 rad model error; acceptable for a soft regularizer; documented).

**Action map (18 dims, action-term order resolved at runtime)**: same L↔R swap; signs
CamShaft −, Hip_Femur +, Femur_Tibia −; same knee approximation (≈0.125 action-units).

**Scan (132)**: GridPatternCfg(resolution 0.15, size [1.65,1.5]) → 12×11; mirror = y-axis flip
of the ray grid; exact flatten ordering to be read from installed isaaclab
patterns.grid_pattern (indexing mode determines permutation). On flat terrain this is ~identity
(constant heights), so the validation run is insensitive to it; still built correctly.

**priv_explicit (9)**: lin_vel_b×2 (+,−,+) then two zeroed 3-blocks with same pattern.
**priv_latent (53)**: mass(1)+, com_b(3)=(+,−,+), friction(1)+, stiffness ratio(24) joint-perm
sign+, damping ratio(24) joint-perm sign+.
**history (870)**: the 87-dim per-step map applied to each of 10 slots.
**critic obs**: dispatch on last-dim; if equal to policy dim apply same map, else raise.

## Plan

1. crab_hex_mirror.py pure module: build_permutation_and_signs(joint_names, action_joint_names,
   scan_order) → index+sign tensors; mirror_obs/mirror_actions/data-augmentation entry point;
   maps built from RESOLVED NAME LISTS, never hand-typed indices.
2. tests: involution mirror(mirror(x))==x (obs+act), permutation validity (bijection),
   per-block sign counts, zeroed-slot consistency.
3. Wiring: symmetry_cfg into the agent cfg used by crab_on_policy_runner (default OFF), enable
   per-run; verify `_env` injection point in on_policy_runner_with_extractor.
4. 100-iter smoke (coef 0.5): symmetry loss logged, decreasing, no NaN.
5. 20k from-scratch validation, PLAIN config (no v5 — seed search: 0/8 v5-active vs 1/1 plain),
   coef 0.5. Mid-checks at 3000/5000 (alternating? duty balanced?), full eval at end vs
   baseline (0.401/+0.209/0.146-0.556). STOP for user with results.
