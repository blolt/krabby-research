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
