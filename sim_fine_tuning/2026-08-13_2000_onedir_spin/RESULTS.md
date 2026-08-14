
## Round 2 (escalation, user-approved): -0.6 / -1.0 — CONCLUSIVE FAIL of the penalty route

| w | reward @3k | 1-dir ratio | completion |
|------|-------|-------|-----|
| -0.6 | 22.7 | 0.004 | 0.7 |
| -1.0 | 1.6 | 0.415 | 0.0 |

The transition is a cliff: -0.6 (~20% of income) still fully absorbed; -1.0 (~33%)
finally produces directionality (ratio 0.42 — proof the policy CAN discover it) but by
collapsing locomotion (standing still, spinning shafts to dodge the tax). No weight both
flips the basin and preserves walking. Penalty route closed on 5-point dose-response.

Remaining options, updated by this evidence:
(b) POSITIVE spin reward (shape toward the basin; -1.0's ratio 0.42 shows the behavior is
    reachable — it needs to be made attractive, not everything else made expensive).
    Candidate term: reward per-shaft signed-consistency (|mean v| / mean |v|) or net
    revolutions per window, gated on nonzero command. Replay gate first per SOP.
(d) ACCEPT oscillation: 20k reference at w=-0.3 (best locomotion; hardware can reverse,
    so transfer is safe). Spin question revisits later (e.g. after tripod consolidates).
Hybrid: (d) now for the reference + (b) as a separate follow-on campaign is also viable.

## 20k run (w=-0.3) certification — SPIN ACHIEVED, stepping un-phased
model_19999 (fromscratch_w0.3_20k/logs/rsl_rl/crab_hex_flat_walk/2026-08-14_08-41-28/):
one_direction_ratio 1.000 (10/10 episodes), shaft 5.99 rad/s continuous, completion 1.0,
reward 19.95; tripod 0.0, slip 29% median, tippy 15%. The campaign's core objective —
the quick-return mechanism driven as designed — is achieved and stable. Stepping phase
never consolidated into tripod within 20k.

Note for next lever: at 6 rad/s the support-swap half-cycle ~= 0.52 s — INSIDE the
reward_tripod_schedule 0.10-0.60 s band (unlike the old oscillation). The inert tripod
term can see this gait.

## Bake decision (user): see chat/AskUserQuestion
