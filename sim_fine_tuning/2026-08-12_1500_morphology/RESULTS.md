# Morphology campaign: plant-side anchors of the lean and duty asymmetry

Successor to three reward campaigns (tripod v1-v5+b6/b7, lean L-series, stride S-series) that
proved the +12° lean and 0.146/0.556 duty split are immune to reward configuration. User
directive 2026-08-12: "move forward with those next steps" (measure, then intervene).

## M1/M2: static measurements (measure_static_posture.py, 300 zero-action steps, 1 env)

| hypothesis | measurement | verdict |
|---|---|---|
| lean anchored in default posture | equilibrium pitch **+0.0096 rad (+0.55°)**, roll −0.33° | **REFUTED** — plant stands level; the lean is a locomotion choice |
| CoM forward of support | longitudinal offset **−3.3 mm** (aft) | **REFUTED** — CoM is on the centroid |
| default pose loads tripod B | static forces: FL 163, FR **252**, ML 134, MR **64**, RL 198, RR 180 N → **A share 42.8%** | **CONFIRMED** — B-tilted 57/43 at zero action, level body; FR carries 4× MR |

The knee-default hand-tune (left −0.07 / right +0.10) balanced roll (L 495 vs R 497 N ✓) but
left the diagonal untouched — and the diagonal is exactly what the tripod sets sample. The
policy's 79/21 duty split is the trained amplification of this 57/43 static seed.

Note: sim total mass 106 kg (body 66) vs URDF reference ~23 kg — the known auto-computed
base-mass discrepancy; irrelevant to the within-sim asymmetry, relevant to sim-to-real later.

## M4: static-load symmetrization (in progress)

Search over default joint angles (per-leg knee, then hip-femur if needed) via the measurement
script's override flag — target all six feet at 165±15 N with pitch/roll ≤1°. Found values then
baked into crab_hex_scene_cfg.py (revertable commit) and validated by M5: fine-tune healthy
19999 on the symmetrized plant, standard two-point eval — watch duty_A, pitch, tripod.
