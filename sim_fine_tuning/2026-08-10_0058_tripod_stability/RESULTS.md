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
