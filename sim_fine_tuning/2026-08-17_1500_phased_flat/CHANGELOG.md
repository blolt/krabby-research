# Phased flat-walk curriculum campaign

Protocol: Task-1 discipline per phase — baseline -> replay gate (new terms) -> one change
per 3k screen -> gait_eval (flat + spin metrics + clearance) -> CHANGELOG row -> commit.
Plasticity telemetry (actor/critic weight norms) recorded at every phase boundary.
L2-init is contingency-only (user decision).

## Phase A — gait stabilization: COMPLETE (no GPU)
Artifact: C2 model_2999 (tripod 0.573, tracking pass, actor norm 26.3 — plastic).

## Phase B — oscillation -> spin (queue)
| arm | config | status |
|-----|--------|--------|
| B0 baseline | resume 2999, KRABBY_REVERSAL_W=-0.3, 3k | queued behind v3 batches 5-6 |
| B1 critic reset | B0 + fresh critic at boundary | pending |
| B2 energy-only | KRABBY_REVERSAL_W=0 + KRABBY_POWER_W=-0.001 | pending |
| B3 dose/spin/lock arms | per plan | pending |
Gates: ratio >= 0.8, tracking < 0.1, completion >= 0.9, tripod >= 0.3, reward >= 0.8x B0.

## Phase C — obstacle introduction (design)
KRABBY_FLAT_TERRAIN_MODE for the flat env (~80/20, difficulty 0.05-0.2, frozen);
build during Phase B screens.

## B0 baseline — COMPLETE 2026-08-17
Resume model_2999 + KRABBY_REVERSAL_W=-0.3, 3k iters (model_5998, 74 min).
Train: reward 28.2, failure 4.4%, ep_len 982, reversal income -0.106 (absorbed).
Eval (10 ep): **one_direction_ratio 0.0055** (pure oscillation, 2.92 reversals/s),
tripod 0.601 (> base 0.573), deficits low/mid/high -0.023/+0.013/+0.092 (tracking PASS),
completion 0.9, slip 10.1%, tippy 20.4%.
Verdict: pressure alone does not convert the gait even on the plastic base — walking
improves, spin unchanged. This is the do-nothing-clever number the arms must beat.
Gates for arms: ratio >=0.8 (win) / >=0.3 (stop-rule floor), deficits <0.1,
completion >=0.9, tripod >=0.3, reward >=22.6 (0.8x B0).
