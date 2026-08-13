# Perpendicular-mounts correction (Arm A: centered yaw defaults)

User hardware clarification 2026-08-13: every leg is mounted perpendicular to the frame with
its yaw range centered on that mount. The config's splay defaults (F/R ±0.342, M ±0.143 —
Go2-inherited proportions) had no hardware basis and parked front/rear legs 8.9° from the
±28.54° mechanism limit at 82% cam gear, with their ±0.24 rad command window off-center —
the root cause of mid-legs-only thrust (see the thrust/DOF analyses in chat + mirror_symmetry
campaign artifacts).

**Change (this commit)**: all 6 hip + 6 camshaft defaults → 0.0 (mount neutral). Standing
stance remains the policy's choice within the command window. Arm B (widening the camshaft
action scale toward the full ±2.07 rad shaft travel = full ±28.54° hip range; today's window
commands only ~±4.4° of yaw) is deferred pending Arm A results.

## Verification ladder

1. **Statics at 0 defaults: PASS** — pitch +0.38°, roll +0.05° (leveler than old pose), A share
   52.6%, CoM +5.7 mm. Load shifted mids-heavy statically (ML/MR ~284 N vs F/R 73–145 N; fore-
   aft spread now from mount spacing only). No self-collision over 300 zero-action steps.
2. Cam operating point (all legs identical now): gear 0.323 (100% of peak), stroke ±28.54°
   symmetric, command window centered — the "after" of the diagnosis table.
3. Fine-tune canary (2000 iters from symmetric reference; expect obs/action re-centering shock;
   catastrophe check only) → then the real validation: 20k from-scratch + mirror loss 0.5.
4. Primary gate: thrust distribution (per-group shaft |v| + reversal share — success = front/
   rear shafts working); plus stride, tripod/duty, lean, standard guardrails.
