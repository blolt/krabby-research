# Stride-definancing campaign (S-series): remove the income financing the duty asymmetry

Successor to `2026-08-12_1017_lean_reduction/` (closed: lean invariant to all penalties). New
mechanism, user-approved 2026-08-12: offline attribution on the baseline traces showed
**98.1% of reward_stride_length income goes to the B tripod set** — only 61/1740 A-set stances
(3.5%) clear the 0.1s `min_phase_duration` payment floor vs 84% of B-set stances, and the floor
(not the power=2 convexity) is the dominant gatekeeper (at power=1 the split stays 97.4% B).
The term that fixed tippy-tap is bankrolling the 0.146/0.556 duty asymmetry; every lean tax was
outbid by this income. The S-series defunds the asymmetry instead of taxing the posture.

## Protocol

Same as the lean campaign: each arm fine-tunes from healthy model_19999, 2000 iters, 256 envs,
seed 1; two-point deterministic gait-eval (mid ~21000 + final ~21998); one change per arm;
serial training, evals overlapped. All changes are Hydra weight/param overrides — no code.

**Success axes**: duty_A rising off 0.146 and/or signed pitch off +0.209 (first structural budge
in three campaigns = KEPT); tripod ≥0.45 at two consecutive checkpoints = bake bar.
**Guardrails** (breach = REVERT): completion=100%, slip ≤3.5%, roll ≥0.03, EMA ≤0.174,
stride ∈[0.11,0.22]m, tippy ≤8% (tippy-tap relapse watch — this campaign touches the anti-tippy
term itself; baseline 6.5%).

## Baseline

tripod 0.401 | pitch +0.209 | duty 0.146/0.556 | pearson −0.606 | stride-income split A/B
1.9%/98.1% | completion 100% | slip 2.6% | roll 0.0387 | EMA 0.134 | stride 0.163 | tippy 6.5%

## Arms

| arm | override(s) | rationale |
|---|---|---|
| S1 | reward_stride_length.params.min_phase_duration 0.1→0.05 | the dominant gatekeeper; lets A-set stances earn at all |
| S2 | params.power 2.0→1.0 + weight 0.5→0.05 (scale-matched, measured 9.5×) | removes concentration preference at constant income magnitude |
| S3 | S1+S2 combined | fully participation-neutral stride income; only if singles move |
| S4 | best mover + reward_tripod_schedule 0.3 | v5 amplifier combo, only if duty/pitch shifts |

## Runs

| S1 | min_phase_duration 0.1→0.05 | mid/final: pitch +0.211/+0.210, tripod 0.405/0.387, tippy 7.0/**6.5%** (NO relapse), duty 0.142/0.557, completion 100/100%, slip 2.3/2.3% | **INERT on structure, instrument validated**: A-set paid stances 3.5%→**43%** (748/1730) — the floor was the participation gate exactly as attributed — but income split only 1.9→4.6% A because power=2 pays an A tap (~0.03m²) 9× less than a B stance (~0.09m²). Floor gates participation; convexity gates income. |

**Sequence adjustment (analysis-driven)**: S2 alone (power=1, floor 0.1) predictably cannot move
the split either — baseline traces at power=1 measure 2.6% A (participation still floor-gated).
S3 (floor 0.05 + power 1.0 + weight 0.05) is the only rule where a marginal A stance is worth
taking (predicted split ~12% A — income can never fully balance while duty is 0.14/0.56, since
income mechanically follows duty; the test is whether marginal-A-incentive changes duty). S3
therefore runs unconditionally after S2; the original "only if singles move" condition was
mis-calibrated against this arithmetic.

| S2 | power 2.0→1.0 + weight 0.5→0.05 (scale-matched) | mid/final: pitch +0.211/+0.209, tripod 0.395/0.420, tippy 7.8/7.0%, completion 100/100%, slip 2.5/2.3%, duty 0.144/0.556 | **INERT as the S1 arithmetic predicted** — with the 0.1s floor still excluding A participation, the exponent has nothing to rebalance. Guardrails clean. Singles complete; S3 (floor+power) is the hypothesis test. |
