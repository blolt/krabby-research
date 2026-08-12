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
