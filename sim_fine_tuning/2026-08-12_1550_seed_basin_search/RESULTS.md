# Seed basin search: run the from-scratch lottery as a deliberate search

User-approved 2026-08-12 ("seed search first, symmetry second and conditional"). Diagnosis
chain: reward campaigns proved lean/duty immune to pricing; morphology campaign proved the
plant innocent (level equilibrium, centered CoM, A/B statically balanced 51±2%); the anchor is
learned symmetry-breaking locked in the baseline's basin, and from-scratch runs sample basins
by lottery (6/6 prior shaped runs missed the alternating basin the plain config found once).

## Protocol

8 from-scratch runs, seeds 2-9, 3000 iters, 256 envs, v5 crossing-credit active at 0.15
(pays ~0 in degenerate basins, amplifies alternating ones — offline-gate proven). Serial
training; each seed's eval (single-point, model_2999, deterministic) overlaps the next seed's
training. Classify each basin:
- **ALTERNATING** if tripod ≥0.25 with anti-phase engagement >5% of steps;
- among alternating, record duty_A/duty_B, signed pitch, and guardrails (completion, slip,
  roll, EMA, stride, tippy).

**Winner** = alternating + best composite (duty_A highest / |pitch| lowest, guardrails clean).
Winner resumes to 20000 (same overrides), final eval vs baseline (tripod 0.401, pitch +0.209,
duty 0.146/0.556); adoption/bake proposal → STOP for user review.
**If zero alternating basins, or all alternating basins are B-handed+leaned** → the symmetry
route is justified by direct evidence; campaign closes with that recommendation (the
conditional trigger the user set).

Reference rows: baseline basin (seed 1, plain config): tripod 0.401, pitch +0.209, duty
0.146/0.556. v5-active seed-1 screen (fromscratch_tripod_v5_crossing_short): unison-glide,
tripod 0.0, pitch +0.131 — counts as seed-1's v5-active sample.

## Seeds

| seed | family | tripod@2999 | pitch | duty_A/B | completion | notes |
|---|---|---|---|---|---|---|
| 2 | bouncy, **A-handed** | 0.078 | +0.182 | **0.633/0.148** (mirror of baseline!) | 80% (2 falls) | slip 9.8%, tippy 23.5%, EMA 0.247; anti-phase 8.9%, 91 swaps. NOT winner-grade, but proves handedness direction is lottery, not plant bias. |
| 3 | tippy-shuffle (skate family) | 0.0 | +0.193 | 0.524/0.504 (balanced but no alternation) | 100% | tippy 38.8%, slip 9.9%, roll collapsed 0.010; anti-phase 0%. Not winner-grade. |
| 4 | unison-glide (falls) | 0.0 | +0.146 | 0.314/0.306 (balanced-light, unison) | 80% (2 falls) | slip 1.2%, tippy 5.5%, roll collapsed 0.013; anti-phase 0%. Clean-looking glide that falls. Not winner-grade. |
| 5 | tippy-shuffle (skate family) | 0.0 | +0.190 | 0.432/0.441 (balanced, no alternation) | 100% | tippy 35.9%, slip 9.2%, roll collapsed 0.011, EMA 0.247; anti-phase 0%. Not winner-grade. |
| 6 | unison-glide (stable) | 0.0 | +0.133 | 0.337/0.342 (balanced-light, unison) | 100% | slip 3.4%, tippy 9.6%, roll collapsed 0.010, EMA 0.126; anti-phase 0%. The seed-1-v5 glide reproduced, this time without falls. Not winner-grade (no alternation). |
| 7 | unison-glide (stable, long-stride) | 0.0 | +0.124 | 0.345/0.318 (balanced-light, unison) | 100% | slip 1.6%, tippy 4.9%, stride 0.218 (at band top), roll collapsed 0.013; anti-phase 0%. Cleanest glide yet — still zero alternation. |

**User visual verdict on seed7 (2026-08-13):** the glide is NOT a good gait — adopt-glide option
rejected. Directive: if seed 8 comes up empty, skip seed 9 and move directly to the symmetry
route (implementation pre-authorized on that condition).
