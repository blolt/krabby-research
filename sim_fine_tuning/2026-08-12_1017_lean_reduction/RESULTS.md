# Lean-reduction campaign: weights-only sweep on existing terms

Goal (user, 2026-08-12): lessen the +12° forward lean and increase tripod score by tuning
weights of EXISTING registered terms only — no new reward functions. Successor to the tripod
campaign (`2026-08-10_0058_tripod_stability/`), which closed with the diagnosis that the duty
asymmetry capping tripod at ~0.40 is postural (anchored by the lean). This campaign tests the
postural hypothesis from the config side. Fully autonomous per user; v5 crossing-credit term
(registered, dormant) allowed in combo arms.

## Protocol

Every arm: fine-tune from healthy baseline model_19999
(`2026-08-09_1526_gait_tuned/logs/rsl_rl/crab_hex_flat_walk/2026-08-09_15-27-14/model_19999.pt`),
2000 iters, 256 envs, seed 1. Gait-eval BOTH the ~1000 and final ~1998 checkpoints (two-point
verdicts; the b7d lesson — single-point verdicts get fooled by checkpoint oscillation). Score:
standard metrics + signed mean pitch + duty_A/duty_B/pearson decomposition. Eval is
deterministic per checkpoint (established 2026-08-12); the yardstick is checkpoint-to-checkpoint
spread (b6 family: ±0.003 tripod).

**Primary target**: signed mean pitch ≤ +0.18 rad at both eval points (baseline +0.209;
improvement ≥0.03 rad). **Secondary**: tripod (win declared only at ≥0.45 on two consecutive
checkpoints). **Guardrails** (any breach at final ckpt = REVERT): completion=100%, slip ≤3.5%,
roll_rms ≥0.03, EMA(v_z) ≤0.174, stride ∈[0.11,0.22]m.

## Baseline reference (model_19999, deterministic protocol)

tripod 0.401 | signed pitch +0.209 | duty_A 0.146 / duty_B 0.556 | pearson −0.606 |
completion 100% | slip 2.6% | roll 0.0387 | EMA 0.134 | stride 0.163 m | tippy 6.5%

## Arms

| arm | override(s) | rationale |
|---|---|---|
| L1 | reward_orientation −0.7→−2.0 | never swept in any campaign; lean contributes ~95% of the term's signal (sin²(12°)=0.043 vs ~0.002 roll) |
| L2 | reward_orientation →−3.5 | escalation, only if L1 partial |
| L3 | penalty_base_pitch_forward_linear 0.0→−0.5 | 2× past Phase A max dose (−0.25 moved pitch ≤1%) |
| L4 | penalty_base_pitch_forward_linear →−1.0 | escalation, only if L3 partial |
| L5 | reward_forward_progress_along_command 0.6→0.3 | Task-1 §2.6 speed-pressure lever, never reached; lean-as-momentum-posture hypothesis |
| L6 | best lean-mover + v5 reward_tripod_schedule @0.3 | only if a single knob moves pitch; b7 evidence: v5 amplifies structure when active (peak tripod 0.425) |

## Runs
