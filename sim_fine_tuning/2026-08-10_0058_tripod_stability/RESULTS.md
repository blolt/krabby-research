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

New dense per-step reward (`reward_tripod_schedule`, `crab_hex_tripod_reward.py`) added per Task 1
§2.3 after Phase A found no config-only knob moves `tripod_score`. Math: coherence*opposition
shape reward (`c_A*c_B*|a-b|/3`, max 1.0 when one tripod is fully planted and the other fully
airborne) gated by an anti-freeze mechanism that zeroes the reward once the dominant tripod has
held >0.6s without a confirmed swap. Registered at weight 0.0, swept here.

| run id | override(s) | iters | tripod | tippy_tap | stride | slip | completion | pitch_rms | verdict |
|---|---|---|---|---|---|---|---|---|---|
| b1_tripod_reward_w0.15 | `reward_tripod_schedule.weight=0.15` | 1000 | 0.4115 (per-ep: 0.43,0.18,0.41,0.37,0.35,0.43,0.41,0.41,0.42,0.39) | 7.83% | 0.164 m | 2.44% | 100% | 0.2122 | REVERTED — essentially baseline-level (0.4115 vs 0.401/0.425), same pattern as every Phase A lever. The dense reward at this weight did not measurably reshape gait behavior within 1000 iterations. |
| b2_tripod_reward_w0.3 | `reward_tripod_schedule.weight=0.3` (2× b1) | 1000 | 0.3884 (per-ep: 0.39,0.42,0.39,0.34,0.39,0.36,0.40,0.36,0.39,0.37) | 6.90% | 0.166 m | 2.18% | 100% | 0.2115 | REVERTED — *lower* than b1 despite double the weight (0.3884 vs 0.4115), no dose-response trend; still within the same ~0.38-0.42 noise band every run this campaign has landed in. Guardrails held (tippy/slip/stride/pitch all fine, if anything slightly better than baseline). |

**Follow-up runs (b3/b4), per explicit user request to try 1-2 more variants before the accept-vs-from-scratch decision:**

| b3_tripod_reward_w0.6 | `reward_tripod_schedule.weight=0.6` (4× b1) | 1000 | 0.3943 (per-ep: 0.37,0.39,0.40,0.39,0.40,0.37,0.40,0.39,0.41,0.41) | 7.17% | 0.167 m | 2.15% | 100% | 0.2123 | REVERTED — further weight escalation confirms no dose-response: 0.15→0.4115, 0.3→0.3884, 0.6→0.3943, no trend, all inside the same band. Guardrails held. |
| b4_tripod_reward_w0.3_maxhold0.3 | `reward_tripod_schedule.weight=0.3`, `params.max_hold_s=0.3` (half default, forces alternation ≥2× more often to keep the reward flowing) | 1000 | 0.4116 (per-ep: 0.43,0.40,0.44,0.40,0.38,0.43,0.41,0.42,0.42,0.40) | 7.24% | 0.164 m | 2.31% | 100% | 0.2119 | REVERTED — the timing lever (not just weight) also fails to move tripod: still squarely in the ~0.38-0.43 band. This was the second of the two mechanistically-distinct remaining ideas (magnitude vs. required-alternation-frequency); both tested, neither worked. Guardrails held. |

## Campaign summary: complete negative result

All 11 fine-tune attempts this campaign (7 config-only Phase A levers + 4 Phase B reward-weight/
timing variants), plus the two Step-0 baseline evals for reference:

| run | tripod | run | tripod |
|---|---|---|---|
| baseline (seed001) | 0.401 | a7_angvel_w-0.05 | 0.412 |
| baseline (seed002, noise calib) | 0.425 | b1_tripod_reward_w0.15 | 0.412 |
| a1_stance_bracket | 0.405 | b2_tripod_reward_w0.3 | 0.388 |
| a3_airtime_w1.2 | 0.389 | b3_tripod_reward_w0.6 | 0.394 |
| a4_airtime_thresh0.10 | 0.383 | b4_tripod_reward_w0.3_maxhold0.3 | 0.412 |
| a5_pitch_w-0.1 | 0.393 | | |
| a6_pitch_w-0.25 | 0.403 | | |

**No run cleared the KEPT gate of 0.45, and none showed a real trend in either direction** — every
value sits inside the ~0.38-0.43 band, indistinguishable from the baseline's own eval-to-eval
noise (0.401 vs 0.425 on identical checkpoints). Neither of the two mechanistically distinct
follow-up ideas worked: weight escalation up to 4× (B1→B2→B3: 0.4115→0.3884→0.3943, no trend) and
tighter alternation timing (B4, `max_hold_s` halved: 0.4116, no different from B1's looser
timing). All guardrails held throughout every one of the 11 runs — no completion failures, no
tippy/stride/slip regressions, no stability regressions from any lever. The fine-tune track is
genuinely exhausted: both magnitude and timing were tested as independent axes and neither moved
the metric.

**Combined with the earlier 14-fine-tune campaign** (a separate, prior campaign that also never
moved tripod off 0.0 across 14 fine-tune attempts with a different reward-shaping approach), there
are now **25 total fine-tune attempts across two independent campaigns and two different reward
designs**, none of which moved tripod score meaningfully — while a single from-scratch training
run reliably reaches ~0.40 with zero reward-code changes. This is strong, repeated evidence that
tripod-phasing quality is substantially determined by from-scratch training dynamics and does not
respond to reward shaping applied on top of an already-converged checkpoint within a short
fine-tune window.

## From-scratch confirmation: reward_tripod_schedule active from training start

Per explicit user request (option 2 of the accept/from-scratch-retrain/more-fine-tune-variants
choice): tested whether the new reward helps when active *from the start* of training, rather
than fine-tuned on top of an already-converged policy. 20000-iter from-scratch flat-walk run,
`env.rewards.reward_tripod_schedule.weight=0.15` (the weight with the tightest per-episode
spread in the fine-tune sweep), otherwise the baked default config. Training completed all 20000
iterations without crashing (`crab_failure` 3.12% in the final windowed block), but training-time
`error_vel_xy` was elevated (0.91 vs. the typical 0.17-0.21 range) — a warning sign that showed up
clearly in the held-out eval.

Checkpoint: `fromscratch_tripod_reward_w0.15/logs/rsl_rl/crab_hex_flat_walk/2026-08-10_20-08-53/model_19999.pt`.

| metric | this run | no-reward from-scratch baseline | fine-tune sweep best |
|---|---|---|---|
| tripod (median) | **0.0** (per-ep: 0,0,0,0,0,0,0,None,0,0) | 0.401 / 0.425 | 0.412 (a7) |
| completion | **50%** (5/10 episodes ended in **fall**) | 100% | 100% |
| tippy_tap | 2.11% | 7.97% | ~7-8% |
| stride (pooled) | **0.488 m** (vs ~0.16-0.17m everywhere else) | 0.163 m | ~0.16 m |
| pitch_rms | 0.260 rad (worse) | 0.211 rad | ~0.21 rad |
| roll_rms | 0.011 rad (much lower) | 0.038 rad | ~0.037-0.038 rad |
| signed mean pitch | 0.243 rad (worse) | 0.209 rad | ~0.21 rad |

**This is a genuine regression, not a null result.** Tripod is exactly 0.0 in every scored episode
— worse than the untrained series' historical 0.0-0.025 range, and half the episodes end in a
fall. The unusually low tippy_tap combined with an unusually large pooled stride and low roll_rms
is consistent with the policy finding a degenerate exploit: rather than learning tripod
alternation, it appears to have converged on an unstable, high-displacement gait pattern
(plausibly moving multiple/all legs together rather than alternating tripods, which would score
exactly 0 on this reward term since `a == b` whenever legs move in unison — the term provides no
gradient signal away from that degenerate solution, and may have interacted badly with the
already-registered `reward_stride_length` term's incentive for long, infrequent stance-phase
displacement). Training-time `error_vel_xy` being 4-5x the typical range was an early warning
sign of exactly this kind of divergence.

**Consequence**: `reward_tripod_schedule` should NOT be enabled (stays at its registered default
of weight=0.0, harmless/inert) — not just "doesn't help" but "actively harmful" when active from
the start of training. Combined with the fine-tune sweep's clean null result, **0.401 (the plain
baked-config from-scratch checkpoint, no tripod-specific reward at all) remains the best tripod
result found across this entire investigation** — 26 total training attempts across two campaigns,
two reward-shaping approaches, and both fine-tune and from-scratch conditions.
