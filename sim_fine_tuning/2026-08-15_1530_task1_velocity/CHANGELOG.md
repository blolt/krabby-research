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

## C2 — air-time threshold 0.05 -> 0.20 s (cam-derived; KRABBY_AIRTIME_THRESH): PASS
| change | reward@3k | tracking deficit (lo/mid/hi) | tripod | completion | slip | tippy |
|--------|-----------|------------------------------|--------|------------|------|-------|
| C1     | 21.0      | +0.08 / +0.03 / -0.01        | 0.0    | 1.00       | 0.079| ~0.15 |
| C2     | **27.1**  | +0.02 / -0.01 / -0.08        | **0.573**| 0.90     | 0.113| 0.238 |
FIRST tripod of the velocity era — exceeds the position-era reference (0.517) at 3k.
Mechanism differed from prediction: micro-taps did NOT drop (19% vs 11% mass <=3 steps);
paying cam-length swings properly reorganized the gait into alternating tripod phasing
instead. WATCH-ITEMS for C3+: tippy 23.8%, slip 11.3%, one fall. Shafts still oscillate
(ratio 0.007) — spin remains a C4+/CPG objective. Stack now = L1 -0.5 + thresh 0.20.

## C3 — stance-count band {3,4}: REFUTED AT REPLAY GATE (no GPU spent)
Position-era reference: 61% of steady steps outside {3,4}; C2: 42%; oscillator: 69%.
The band assumes 50%-duty alternation; this mechanism's tripod runs ~0.66 duty with
legitimate 4-6-contact overlap. Term skipped per Task 1 s2.3/NOTE discipline. If a
fall-pricing term is needed later (positive spin terms reintroduced), derive the band
from the certified reference's own count distribution and drop the steady-mask
dependence (fallen traces have no steady steps to score).

## C1+C2 20k adoption run: CERTIFICATION FAIL (basin roulette)
model_19999: tripod 0.0 (never consolidated — same config+seed as the 0.573 screen; GPU
nondeterminism), completion 0.8, slip 16.7%, tippy 27.9%, high-hold deficit -0.14 (over
gate). Tracking substantially held. Income telemetry identical to the screen — the basin
difference is phase coordination, invisible in reward magnitudes.

## C3b proposal (recovery): tripod crossing term as consolidation lock
Replay on the C2 screen's tripod traces: 16.3/min @0.15 weight, 158 crossings/min — vs
~0 on every non-tripod family ever traced. The v1-v5-refuted term finally has a gait
that earns it: self-reinforcing once the basin is entered, inert otherwise. Plan:
enable reward_tripod_schedule 0.15 on C1+C2 -> 4-seed x 3k selection (pick tripod
formers) -> resume best +17k -> re-certify. (~overnight GPU)

## C3b — tripod crossing lock @0.15: FAIL (income 0.0000 all run — basin never entered)
Confirms the v-series theorem in the velocity era: the term is a lock, not a creator.
Tracking regressed (deficits -0.09/-0.17/-0.30), reward 19.5 < gate. REVERTED.
Basin-entry conclusion after 7 attempts across 2 campaigns: entry is not
reward-addressable — only SELECTION (multi-seed) or STRUCTURE (CPG) remain.
Task-1 flat-walk list status: 2.1 C2-PASS, 2.2 baked, 2.3 refuted+lock-only,
2.5 C5 re-sweep REMAINING, 2.6 C1-PASS.
