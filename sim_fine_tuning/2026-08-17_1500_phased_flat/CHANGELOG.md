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

## B1 critic reset — COMPLETE 2026-08-17 — NEGATIVE
Surgery: fresh critic (norm 30.7->17.3), Adam cleared; resume + reversal -0.3, 3k
(model_5998). Train: reward 24.4, failure 7.5%, reversal income -0.108 (absorbed).
Eval: ratio 0.0057 (no conversion, 3.03 rev/s), tripod 0.450 (<< B0 0.601),
completion 0.8 (FAIL), high-hold deficit +0.111 (FAIL), slip 12.5%, tippy 28.7%.
Verdict: critic reset at the B boundary does not enable conversion and costs walking
quality. Combined with the v2-base falsification (lit review §5), the primacy-bias
hypothesis is now negative in BOTH the rigid and plastic settings — drop critic reset
from the remaining Phase-B/C candidate lists except as a no-cost adjunct.

## B2 energy-only — COMPLETE 2026-08-17 — NO CONVERSION, best walker
KRABBY_REVERSAL_W=0 + KRABBY_POWER_W=-0.001, resume model_2999, 3k (model_5998).
Train: reward 18.9 (power income -0.74 dominates the gap), failure 5.1%, ep_len 960.
Eval: ratio 0.0056 (no conversion; reversals 2.62/s, mildly down), tripod **0.621**
(best yet), tippy 18.9% (best), slip 10.5%, completion 0.9, deficits -0.014/+0.010/
+0.076 (all PASS). Verdict: the physics cost gradient improves gait quality across the
board but cannot bootstrap the oscillation->spin flip on its own — the 42%-cheaper spin
basin is separated by a barrier the local gradient doesn't cross. Candidate keeper as a
quality term regardless of spin outcome.

## Ratio scoreboard after singles round 1
B0 pressure -0.3: 0.0055 | B1 critic reset: 0.0057 | B2 energy: 0.0056.
Remaining singles: B3a spin reward +0.2 (positive income on the EMA spin metric — only
untried mechanism class), then phase-lock +0.1 / reversal dose -0.6 if needed.
Stop rule floor (no arm >= 0.3) not yet triggered — singles not exhausted.

## B3a spin reward +0.2 — COMPLETE 2026-08-17 — NO CONVERSION
Baseline stack + KRABBY_SPIN_REWARD_W=0.2, resume model_2999, 3k (model_5998).
Train: spin income 0.009/0.2 (EMA ratio ~5% throughout — never bootstrapped), reward
26.9, failure 10.3%. Eval: ratio 0.0043, tripod 0.569, completion 1.0, deficits
-0.024/+0.004/+0.090 (PASS), slip 10.3%, tippy 24.3%, 2.95 rev/s.
Verdict: positive income on the spin metric cannot bootstrap from a ~0 base — the EMA
gate means near-zero gradient until spinning already exists. Fourth mechanism at
ratio ~0.005. Remaining singles: B3b phase-lock +0.1, B3c reversal dose -0.6.

## B3b phase-lock +0.1 — COMPLETE 2026-08-17 — NO CONVERSION
Baseline stack + KRABBY_PHASE_LOCK_W=0.1, resume model_2999, 3k (model_5998).
Train: phase-lock income 0.005/0.1 (same bootstrap failure as B3a — pays only for
cam-consistent contacts, which don't exist at ratio ~0.005), reward 28.2, failure 3.5%.
Eval: ratio 0.0045, tripod 0.563, **completion 0.6 (4 falls — worst arm)**, deficits
PASS, 2.95 rev/s. Verdict: null on spin, negative on robustness. Fifth mechanism null.

## B3c reversal dose -0.6 — COMPLETE 2026-08-17 — ABSORBED
KRABBY_REVERSAL_W=-0.6, resume model_2999, 3k (model_5998). Train: reversal income
-0.193 (~2x the -0.3 income = unchanged reversal rate), reward 26.7, failure 6.0%.
Eval: ratio 0.0042, tripod 0.543, completion 0.6 (4 falls), deficits PASS, 2.90 rev/s.

## PHASE B SINGLES ROUND CLOSED — STOP RULE TRIGGERED 2026-08-17
Six mechanisms, one change per screen, all from the plastic C2 base, all ratio ~0.005
(gate floor 0.3): B0 pressure -0.3 (0.0055), B1 critic reset (0.0057), B2 energy
attraction (0.0056), B3a spin income +0.2 (0.0043), B3b phase-lock +0.1 (0.0045),
B3c pressure -0.6 (0.0042). No arm moved the ratio AT ALL — the oscillation basin is
not escapable by reward shaping from this base, plastic or not. Per the plan's stop
rule: hard stop, user fork required before combos or structural changes.
Best walker artifact of the round: B2 model_5998 (tripod 0.621, tippy 18.9%, all
non-spin gates PASS) — candidate Phase-C base if the fork de-scopes spin from Phase B.

## COMBO ROUND — COMPLETE 2026-08-18 03:35 — ALL SIX NULL ON SPIN
Six overnight combo screens (run_combo_round.sh), all 3k resumes from the C2 base:

| arm | stack | ratio | tripod | completion | failure | rev/s |
|---|---|---|---|---|---|---|
| CB1 | pow+rev0.3 | 0.0072 | 0.604 | 1.0 | 3.3% | 2.54 |
| CB2 | pow+rev0.3+spin0.2 | 0.0064 | 0.605 | 0.9 | 2.3% | 2.59 |
| CB3 | pow+spin0.2 | 0.0052 | 0.593 | 1.0 | 2.7% | 2.59 |
| CB4 | pow+rev0.6 | 0.0062 | **0.635** | 1.0 | **1.9%** | 2.56 |
| CB5 | rev0.3+spin0.2+lock0.1 | 0.0052 | 0.574 | 0.8 | 2.6% | 2.82 |
| CB6 | all four | 0.0053 | **0.649** | 0.9 | 3.9% | 2.63 |

Best ratio 0.0072 (CB1) — noise-level, ~40x below the 0.3 stop-rule floor. The energy
backbone again bought gait quality (CB6 tripod 0.649 = best-ever; CB4 failure 1.9% =
best-ever) and shaved reversals to ~2.55/s, but no combo initiated conversion.
PHASE B REWARD-SHAPING IS EXHAUSTED: 12 arms (6 singles + 6 combos) spanning pressure,
attraction, income, timing, surgery, and their combinations — ratio never left
[0.004, 0.008]. Conclusion stands: the oscillation basin is structurally inescapable
by reward shaping; remaining forks are structural (unidirectional cam action clamp)
or de-scope (Phase C from the best walker). Best walker artifacts now: CB6 model_5998
(tripod 0.649) and CB4 model_5998 (failure 1.9%, tripod 0.635, completion 1.0).
