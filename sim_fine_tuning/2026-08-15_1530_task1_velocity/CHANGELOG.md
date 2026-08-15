# Task-1 velocity-era campaign (disciplined restart)

Protocol (per M18 TASK-1-REWARD-SHAPING.md s3 + campaign SOP):
- ONE change per run; replay gate before every screen; 3k from-scratch screens
  (seed 1, 256 envs); scored vs B0 with the Task-0 harness (flat_walk_forward);
  every change gets a before/after CHANGELOG row; reverted attempts documented.
- Certification gates AMENDED: full battery + per-hold tracking deficit < 0.1 m/s
  + training tracking income recorded.
- Effective reward stack at campaign start = position-era bake (unbake commit cc30e3c);
  instruments registered at 0.0 behind env vars.

## B0 baseline (adopted, no GPU): fromscratch_velact_short (geometry campaign)
| change | reward@3k | tracking deficit (lo/mid/hi) | 1-dir ratio | completion | slip | tripod |
|--------|-----------|------------------------------|-------------|------------|------|--------|
| B0     | 21.0      | +0.25 / +0.08 / -0.10        | 0.006       | 0.90       | 0.079| 0.0    |

## Change queue (audit-verdict order)
C1 tracking restoration (linear |v_err| penalty; fallback arm: + sigma^2 0.25)
C2 air-time threshold recalibration from cam kinematics (return stroke = 2.14 rad/omega)
C3 stance-count band penalty {3,4} (also prices fall-and-spin)
C4+ spin instruments one at a time, re-gated on tracking-era traces
ESC CPG action space (structural; separate plan)

## C1 — linear tracking penalty (KRABBY_TRACK_L1_W=-0.5): PASS (all gates)
| change | reward@3k | tracking deficit (lo/mid/hi) | 1-dir ratio | completion | slip | tripod |
|--------|-----------|------------------------------|-------------|------------|------|--------|
| B0     | 21.0      | +0.25 / +0.08 / -0.10        | 0.006       | 0.90       | 0.079| 0.0    |
| C1     | 21.0      | **+0.08 / +0.03 / -0.01**    | 0.005       | **1.00**   | 0.079| 0.0    |
First command-following policy of the velocity era. Mechanism confirmed: L1's constant
gradient carried the policy into the narrow exp well (tracking-exp income 0.76/1.25 vs
era's 0.25 flatline, sigma^2 still 0.02). Speed modulation comes from legs, not shaft
cadence (shaft |w| ~5.6 at all holds). C1 retained via env var for subsequent screens;
bake decision deferred to campaign end per SOP.
