# One-direction spin campaign (velocity-era reference)

Goal: certified velocity-era flat-walk reference with sustained one-direction shaft spin.
SOP: offline replay gate -> 3000-it weight screens -> 20k from-scratch -> certification.
Approved plan: full autonomous chain; two arms (-0.1, -0.3); teacher carry-up deferred.

## Step 1: spin metrics (DONE)
shaft_spin_metrics() in gait_eval/metrics.py + report.py wiring + aggregate stats
(shaft_one_direction_ratio, shaft_mean_abs_vel). 3 new unit tests (26 pass). Validated
offline vs velact npz: mean|v| 5.606 (ad hoc 5.61), ratio 0.0057, reversals 2.85/s.

## Step 2: reversal-term replay gate (DONE, PASS)
offline_replay/replay_reversal_gate.py. Degen oscillator: 21.5 unweighted rev*dt/min ->
-0.1 = 3.3% and -0.3 = 9.9% of locomotion income (both in the 3-15% window); synthetic
one-direction spin pays exactly 0 (sticky rule verified). Context: the position-era
reference gait would have paid 2.6x more (55.8/min) -- explains why the term hurt then.

## Step 3: weight screens (KRABBY_REVERSAL_W env override added to
CrabHexFlatWalkRewardsCfg.__post_init__; default 0.0 until bake)
Progression rule per arm: (i) one_direction_ratio median >= 0.8, (ii) completion >= 0.9,
(iii) final reward >= 0.8x w0 control (>= ~17), (iv) mean |shaft v| >= 3 rad/s.
w0 control = geometry campaign fromscratch_velact_short (reward 21.0, ratio 0.006).

## Step 3 verdict: BOTH ARMS FAIL the spin criterion — HARD STOP (per plan)

| arm | reward @3k | 1-dir ratio | reversals/s | tripod | completion | slip |
|-----|-----------|-------------|-------------|--------|------------|------|
| w=0 control | 21.0 | 0.006 | 2.85 | 0.0 | 0.9 | 7.9% |
| -0.1 | 17.7 | 0.013 | 3.49 | 0.0 | 0.9 | — |
| -0.3 | 27.1 | 0.005 | 2.87 | **0.139** | **1.0** | 4.8% |

Reading: the penalty (up to ~10% of locomotion income) does not move the policy off the
oscillation attractor at all — reversal rates are unchanged; policies absorb the cost.
Unexpectedly, -0.3 produced the best velocity-era locomotion yet (reward 27 @ 3k = the
position-era 20k reference level; first nonzero tripod 0.139; completion 1.0; slip 4.8%)
— the reward gain is real gait improvement, not penalty avoidance. Mean |shaft v| stays
~5.6 rad/s in all arms (shafts never suppressed).

Design fork (user decision): see RESULTS.md.
