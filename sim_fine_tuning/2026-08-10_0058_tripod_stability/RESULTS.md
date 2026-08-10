# tripod_stability: tripod-first reward tuning campaign

Autonomous weight/param sweep campaign, per the plan approved 2026-08-10 (`~/.claude/plans/the-newest-version-of-cheerful-codd.md`), following TASK-1-REWARD-SHAPING.md priorities in order: (1) improve `tripod_score`, (2) don't degrade tippy/stride/slip/completion, (3) improve upright stability (the user observed the current gait leans forward and isn't always stably supported by planted legs).

Every run is a **flat-walk-only**, 1000-iter resume from the baseline checkpoint (`2026-08-09_1526_gait_tuned/logs/rsl_rl/crab_hex_flat_walk/2026-08-09_15-27-14/model_19999.pt`), with overrides via Hydra CLI (`env.rewards.<term>.weight=X`, `env.rewards.<term>.params.<p>=Y`) — no code changes for weight/param exploration. Each run is gait-eval'd (`--scenario flat_walk_forward`) and scored **only** on gait-eval (training-time metrics have previously diverged from held-out gait quality — see `2026-08-09_1526_gait_tuned/CHANGELOG.md`'s T2-extension finding).

## Baseline (reference row)

Checkpoint: `2026-08-09_1526_gait_tuned/logs/rsl_rl/crab_hex_flat_walk/2026-08-09_15-27-14/model_19999.pt`. Two independent gait-evals (seed001, the original; seed002, a repeat run for noise calibration):

| eval | tripod (median) | tippy_tap | stride (pooled) | slip | completion | pitch_rms | roll_rms | signed mean pitch |
|---|---|---|---|---|---|---|---|---|
| seed001 (original) | 0.4011 (range 0.359-0.453 / 10ep) | 7.97% | 0.163 m | 2.31% | 100% | 0.211 rad (12.1°) | 0.038 rad | +0.209 rad (12.0°) |
| seed002 (noise calib) | 0.4249 | 7.19% | — | 2.33% | 100% | — | — | +0.210 rad (12.0°) |

**Noise floor**: |tripod delta| = 0.024, well inside the plan's default 0.05 — the KEPT gate stays at **≥0.45**, no widening needed.

**Stability baseline is highly repeatable**: signed mean pitch was +0.209 rad and +0.210 rad across the two independent evals (essentially identical), and per-episode pitch never came close to zero in either run (min 0.122 rad across all 10+10 episodes) — confirming a **sustained structural forward lean** (~12°), not noise or oscillation. Roll is much smaller (~0.038 rad RMS, ~2.1°) and not a concern. This quantifies the user's visual observation.

## Decision gates

| metric | KEPT threshold | hard guardrail |
|---|---|---|
| tripod (median/10ep) | ≥ 0.45; borderline: ≥7/10 episodes above 0.401 | ≥ 0.35 (a stability win that costs tripod is REVERTED) |
| completion | — | = 100% |
| tippy_tap | bonus | ≤ 9.0% |
| stride (pooled n_td-weighted) | — | ≥ 0.150 m |
| slip | — | ≤ 3.0% |
| pitch/roll (stability levers only) | KEPT if \|mean pitch\| ↓ ≥25% or pitch_rms ↓ ≥15% (with tripod ≥ 0.35) | pitch_rms & roll_rms ≤ 1.15× baseline (every run) |

## Runs

| run id | override(s) | iters | tripod | tippy_tap | stride | slip | completion | pitch_rms (Δ vs base) | verdict |
|---|---|---|---|---|---|---|---|---|---|
| a1_stance_bracket | `penalty_excess_feet_contact_forward.params.max_feet_on_ground=3`, `reward_stance_support_feet_when_forward.weight=0.1` | 1000 | 0.4045 | 7.92% | 0.161 m | 2.50% | 100% | 0.2117 (+0.0008) | REVERTED — essentially flat vs baseline (0.4045 vs 0.401/0.425 across the two baseline evals, well inside noise); all guardrails held (pitch/roll unchanged) but the stance-count bracket alone doesn't move tripod within 1000 iters. A2 (stronger dose) skipped per the plan's flat-result rule — moving to A3. |
| a3_airtime_w1.2 | `reward_feet_air_time_positive.weight=1.2` (0.8→1.2) | 1000 | 0.3887 | 7.35% | 0.167 m | 2.21% | 100% | 0.2122 (+0.0013) | REVERTED — tripod actually slightly *below* baseline (0.389 vs 0.401/0.425), not an improvement; tippy/stride/slip all improved modestly but that's secondary to the primary tripod target. Guardrails held. |
| a4_airtime_thresh0.10 | `reward_feet_air_time_positive.params.threshold=0.10` (0.05→0.10, weight stays 0.8) | 1000 | 0.3827 | 8.04% | 0.169 m | 2.22% | 100% | 0.2141 (+0.0032) | REVERTED — same pattern as A3, tripod again slightly below baseline (0.383). Neither air-time weight nor threshold moves tripod on their own; the air-time term appears orthogonal to tripod phasing. Guardrails held. |
| a5_pitch_w-0.1 | `penalty_base_pitch_forward_linear.weight=-0.1` | 1000 | 0.3930 | 7.00% | 0.165 m | 2.39% | 100% | 0.2124 (+0.0016); **signed mean pitch 0.2105 rad vs baseline 0.2095 rad (essentially unchanged, +0.5%)** | REVERTED (stability) — the pitch penalty at -0.1 had almost no measurable effect on the forward lean (needed ≥25% reduction, got ~0%); at this weight it's too weak relative to the track/forward-progress rewards. Tripod again below baseline. Escalating dose to A6. |
| a6_pitch_w-0.25 | `penalty_base_pitch_forward_linear.weight=-0.25` (2.5× A5) | 1000 | 0.4027 | 7.14% | 0.163 m | 2.09% | 100% | 0.2129 (+0.0020); **signed mean pitch 0.2109 rad vs baseline 0.2095 rad (still essentially unchanged, +0.7%)** | REVERTED (stability) — even at 2.5× A5's weight, the lean barely moved (needed ≥25%, got ~0%). This penalty appears to have very little leverage over the sustained forward lean within a 1000-iter fine-tune, at either weight tried. Tripod back near baseline (0.403). No pathology (tippy/stride/slip all fine). |
| a7_angvel_w-0.05 | `reward_ang_vel_xy.weight=-0.05` (0→-0.05) | 1000 | 0.4123 | 6.83% | 0.164 m | 2.27% | 100% | 0.2118 (+0.0009); roll_rms 0.0373 vs baseline 0.0376 (unchanged); **signed mean pitch 0.2100 rad vs baseline 0.2095 rad (unchanged), signed mean roll -0.0250 rad vs baseline -0.0250 rad (unchanged)** | REVERTED (stability) — angular-velocity damping had no measurable effect on either pitch or roll (both static bias and RMS). Tripod ~baseline (0.412). |

## Phase A summary

**Clean negative result across all 7 config-only knobs.** No run reached the tripod KEPT gate
(≥0.45); the best individual result was A7 at 0.4123, indistinguishable from baseline noise
(0.401/0.425 across two Step-0 evals). Three runs (A3, A4, A6-adjacent) landed slightly *below*
baseline. None of the three stability levers (A5/A6 pitch penalty at two doses, A7 angular-velocity
damping) moved the signed mean pitch by more than ~1% despite up to 2.5× weight escalation on the
pitch penalty — the sustained ~12° forward lean appears to have very little leverage from any of
these terms within a 1000-iteration fine-tune. No guardrail violations occurred in any run (all
held completion=100%, tippy/stride/slip within bounds). Per the plan, this triggers Phase B: an
explicit dense tripod contact-schedule reward.

## Phase B: explicit tripod contact-schedule reward
