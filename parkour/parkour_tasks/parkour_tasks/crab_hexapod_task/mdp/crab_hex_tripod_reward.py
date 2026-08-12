"""Pure-torch tripod-alternation reward math for the crab hexapod (Milestone 18 Task 1 follow-on).

Config-only reward-weight/param sweeps (`sim_fine_tuning/2026-08-10_0058_tripod_stability/`) found
that no combination of existing terms -- a stance-count bracket at exactly 3, air-time weight/
threshold, a signed forward-pitch penalty at two doses, or angular-velocity damping -- meaningfully
moved the gait-eval harness's `tripod_score` (`gait_eval/metrics.py`) within a 1000-iteration
fine-tune from a checkpoint that already scores 0.401 on it. This term is the explicit
contact-schedule reward anticipated by Task 1 §2.3 ("reward alternating 3-foot stance sets... only
if air-time/stride do not produce regular phasing").

It is a dense, per-step proxy for the same quantity the eval metric measures over a whole steady
window: `tripod_score = 0.5 * (coh_A + coh_B) * max(0, -corr(a, b))`, where `a`/`b` are the
per-step stance counts of tripod sets A = {FL, MR, RL} and B = {FR, ML, RR} (`TRIPOD_A`/`TRIPOD_B`
in `gait_eval/metrics.py`) -- a real tripod alternates the two sets as units, so a good gait has
both high within-set coherence (both feet-in-a-set touch down/lift off together) and strong
anti-correlation between the sets (one is planted while the other swings).

Per step: each foot's raw contact state is treated as "in stable contact" only once it has
persisted continuously for ``debounce_s`` (matches the ``last_contact_time`` flicker-rejection
role in ``crab_hex_stride_reward.stride_length_reward_step``, but applied per-step rather than
only at liftoff, since this term needs a live stance count every step, not just at phase
transitions). ``a``/``b`` are the counts of stably-contacting feet in each tripod set (0-3).
Coherence is `1.0` only when a set is fully planted (3) or fully airborne (0) -- anything in
between (a leg out of sync with its own tripod) scores 0 for that set. The shape reward
`c_A * c_B * |a - b| / 3` is maximal (`1.0`) exactly when one tripod is fully planted and the
other fully airborne.

A pure state-coherence reward would let the policy farm reward by freezing in one tripod stance
forever (that state is coherent and maximally "opposed" even though nothing is alternating) -- the
eval's anti-correlation term is what actually penalizes that, since a constant `a`/`b` has zero
variance and thus zero correlation, but `max(0, -corr)` degenerately reports 0 for a frozen signal
(see `tripod_window_metrics`'s ``degenerate_anti_phase`` handling), not a reward. This module's
anti-freeze gate reproduces that requirement directly: it tracks which tripod set is currently
"dominant" (the sign of `a - b`, only once the count gap is at least 2 and that gap's sign has
itself persisted for ``min_swap_interval`` -- debouncing the *swap* separately from debouncing
individual foot contacts) and zeroes the reward once the dominant set has held for longer than
``max_hold_s`` without a confirmed swap. Genuine alternation keeps resetting the hold timer and
keeps the reward flowing; a frozen stance does not.

Reward is zero whenever the commanded planar speed is below ``min_cmd_norm`` (matches
``reward_forward_progress_along_command`` and the stride-length term's gating -- no reward for
standing still or pure in-place turning, where "tripod gait" isn't a meaningful concept).

**v2 addendum (in-band stance-count support bonus).** v1 of this term -- just the shape reward
and anti-freeze gate above -- caused a catastrophic regression when trained from scratch (see
`sim_fine_tuning/2026-08-10_0058_tripod_stability/RESULTS.md`): the policy converged on a unison
lunging gait (all legs moving together, flight phases, 0.488m strides, half the eval episodes
ending in falls). Two structural flaws enabled that: (1) unison motion keeps ``a == b`` at all
times, so ``|a - b| = 0`` and v1 scored it exactly 0 -- no gradient *away* from the exploit, only
a failure to reward it; (2) the anti-freeze gate zeroes ``r_shape`` for any never-swapping policy
within 0.6s of episode start, so even a policy drifting *toward* alternation earned nothing until
it produced a full confirmed swap -- a coordination cliff v1 never climbed.

v2 adds the Task 1 §2.3 stance-count band constraint ("penalize stance counts outside {3, 4}
during commanded motion") -- but as its reward-dual, an in-band **support bonus**, because
``ParkourRewardManager.compute`` clips the summed per-step reward at zero (legged-gym
convention): a literal penalty would be silently clipped away exactly during the exploit's
flight/all-down phases, where the other terms already sum non-positive. Under PPO advantage
normalization the bonus is the same shaping as the penalty, but it survives the clip:

    support = 1 - relu(3 - total)/3 - relu(total - 4)/2   (total = a + b, debounced)

i.e. count 0 (flight) -> 0, 1 -> 1/3, 2 -> 2/3, counts 3-4 (proper tripod / double-stance) -> 1,
5 -> 1/2, 6 (all-down) -> 0. The asymmetric normalization pins *both* halves of the unison
exploit at exactly 0, and the graded ramp at counts 1/2/5 is the mechanism that gives the
escape path a slope (a binary in-band indicator would recreate v1's flat-zero surface).
Critically, the support term is **not** gated by the anti-freeze timer -- a policy drifting
toward keeping one tripod planted earns strictly increasing reward from the first step, no
confirmed swap required. The accepted trade-off is that a parked in-band stance earns
``support_scale`` from this term indefinitely; the tracking/forward-progress/foot-idle terms
are what make parking a net loss overall.

**v3 addendum (body-stability gate on the support bonus).** v2's from-scratch test converged on
a tip-over-and-correct unison gait (see the campaign RESULTS.md): the support bonus fixed v1's
falls (100% completion) but counts planted *feet*, not body *attitude* -- a tipping robot passes
through 3-4-feet-down configurations and farms the bonus while rocking all six legs in unison
(tripod 0.0 throughout, roll_rms collapsed to 0.014 vs the healthy 0.038). v3 multiplies the
support half (only) by a stability gate. The gate signal was chosen from measured eval data, not
intuition -- pitch magnitude cannot discriminate (degenerate pitch_rms 0.2095 vs healthy 0.211,
both dominated by the healthy gait's own sustained ~12deg lean) and body angular rates are
*anti*-discriminative (healthy ``|w_xy|`` 0.72 vs degenerate 0.55 rad/s -- the rocking is
smoother than walking's leg-cycle jitter). The clean separator is EMA-smoothed world-frame
vertical speed: healthy episodes p95 <= 0.237 m/s vs v2-degenerate p05 >= 0.362 (no overlap;
cross-validated against v1's lunge). Causally sound: every exploit found so far pumps the CoM
vertically, while a tripod gait's whole point is keeping it level.

    s = EMA(|v_z_world|, tau=0.5s);   gate = clamp((hi - s) / (hi - lo), 0, 1)

with ``(lo, hi) = (0.20, 0.50)``: a clamped linear ramp, not a binary threshold (advantage-noise
cliff + v1-style flat-zero surface) and not an exponential (which would apply shaping pressure
inside the healthy band). The flat-1 shoulder above the healthy band means the healthy gait's
own vertical dynamics are completely unpenalized (measured transmission 0.996), while the ramp
keeps a nonzero slope across most of the degenerate EMA range (0.36-0.62) so an exploit that
bounces less earns measurably more -- an escape slope, not a cliff. The EMA state must reset to
0 (gate fully open) on episode reset, or freshly-reset envs would inherit a closed gate and
healthy post-reset exploration would go unrewarded.

**v4 addendum (event-based swap credit; support bonus and v_z gate REMOVED).** Four consecutive
from-scratch failures told one story (see the campaign RESULTS.md): v1 -> unison lunge, v2 ->
tip-and-correct rock, v3 -> level-bodied skate-shuffle, v3b (v3 + a feet_slide penalty) ->
near-stationary drag. Each version's gate eliminated its target behavior, and each time the
policy relocated to the cheapest remaining **state-holding** strategy that satisfied the current
gate set -- because the support bonus paid for holdable *states*, and its clip-immune income
stream was the constant across every exploit (while penalties like feet_slide were muted by the
manager's zero-floor clip exactly in those basins). Meanwhile the plain baked config reaches
tripod 0.34-0.40 emergently, earning its income from *motion* (tracking, forward progress).

v4 therefore abandons state-based income entirely. The support bonus and its v_z stability gate
are removed (nothing worth gating remains), and the term's income becomes **event-based**: a
lump credit is paid exactly on the step a dominant-set swap is *confirmed* (the same debounced
detection the anti-freeze timer already uses -- sign(a-b) with |a-b| >= 2 persisting
``min_swap_interval``), scaled by the opposition quality ``|a-b|/3`` at the confirm step. A swap
physically requires lifting one tripod set and planting the other; no static configuration --
frozen stance, all-down statue, flight, level drag -- produces confirmed swaps, so no holdable
state earns anything. And "farming" swap events faster is not an exploit: rapid genuine
alternation of the tripod sets *is* the target behavior. The per-step shape channel
(``r_shape * anti_freeze``) is kept unchanged -- it pays during sustained coherent alternation
and remains worth 0 to every degenerate family observed. ``swap_credit`` (default 15.0) sizes
the lump so that at a healthy alternation cadence (~3 swaps/s) the event income is comparable to
what the shape channel pays during perfect alternation. Unlike v1-v3, this term no longer tries
to *create* phasing from nothing; it amplifies and sharpens the alternation the base config
already produces emergently.

See ``RewardTripodSchedule`` in ``parkour_isaaclab/envs/mdp/rewards.py`` for the stateful
``ManagerTermBase`` wrapper that drives this from real env/sensor data (specifically
``ContactSensor.data.current_contact_time``, which already gives the "seconds continuously in
contact" signal this module debounces against, the same sensor derivative
``RewardStrideLength`` uses); this module stays free of any ``isaaclab`` import so it can be
unit-tested without Isaac Sim, matching ``crab_hex_stride_reward.py``'s own isolation pattern.
"""

from __future__ import annotations

from typing import Sequence

import torch

#: Foot-order convention shared with ``gait_eval/metrics.py``'s ``FOOT_ORDER`` and
#: ``_CRAB_FOOT_BODY_NAMES`` in ``parkour_mdp_cfg.py`` -- (FL, FR, ML, MR, RL, RR).
TRIPOD_A_IDX: tuple[int, ...] = (0, 3, 4)
"""Index positions of tripod set A = {FL, MR, RL} within the 6-foot ``FOOT_ORDER`` convention."""
TRIPOD_B_IDX: tuple[int, ...] = (1, 2, 5)
"""Index positions of tripod set B = {FR, ML, RR} within the 6-foot ``FOOT_ORDER`` convention."""


def tripod_schedule_reward_step(
    current_contact_time: torch.Tensor,
    command_xy: torch.Tensor,
    candidate_sign: torch.Tensor,
    candidate_streak: torch.Tensor,
    confirmed_sign: torch.Tensor,
    time_since_confirmed_swap: torch.Tensor,
    dt: float,
    tripod_a_idx: Sequence[int] = TRIPOD_A_IDX,
    tripod_b_idx: Sequence[int] = TRIPOD_B_IDX,
    min_cmd_norm: float = 0.12,
    debounce_s: float = 0.08,
    min_swap_interval: float = 0.1,
    max_hold_s: float = 0.6,
    swap_credit: float = 15.0,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    """One step of the tripod-alternation reward's state machine.

    Args:
        current_contact_time: ``[N, 6]`` seconds each foot has been continuously in contact (0.0
            if not currently in contact), in ``FOOT_ORDER`` -- e.g.
            ``ContactSensor.data.current_contact_time``.
        command_xy: ``[N, 2]`` commanded planar velocity (body frame).
        candidate_sign: ``[N]`` state in -- the most recently observed raw dominant-set sign
            (``-1``, ``0``, or ``1``), before this step's debounce update.
        candidate_streak: ``[N]`` state in -- seconds ``candidate_sign`` has persisted
            continuously.
        confirmed_sign: ``[N]`` state in -- the last *confirmed* dominant-set sign (only updates
            once a candidate has persisted ``min_swap_interval``).
        time_since_confirmed_swap: ``[N]`` state in -- seconds since ``confirmed_sign`` last
            changed to a new confirmed value.
        dt: physics step duration (s).
        tripod_a_idx: index positions (into the 6-foot axis) of tripod set A.
        tripod_b_idx: index positions (into the 6-foot axis) of tripod set B.
        min_cmd_norm: below this commanded planar speed there's no defined gait direction, so no
            reward (matches ``reward_forward_progress_along_command``).
        debounce_s: a foot counts as "in stable contact" only once ``current_contact_time`` for it
            exceeds this -- rejects a single spurious contact-sensor step from moving the count.
        min_swap_interval: a new raw dominant sign must persist this long before it's accepted as
            a genuine swap (debounces swap detection separately from per-foot contact debounce).
        max_hold_s: the shape reward is zeroed once the confirmed dominant set has held longer
            than this without a new confirmed swap -- forces alternation rather than a static
            coherent stance, mirroring the eval metric's degenerate-signal handling.
        swap_credit: lump reward paid on the step a dominant-set swap is confirmed, scaled by
            the opposition quality ``|a - b| / 3`` at that step (see the v4 addendum). Sized so
            that at a healthy alternation cadence (~3 swaps/s) the event income is comparable to
            the shape channel's payout during perfect alternation. Event income cannot be farmed
            by any static configuration -- a confirmed swap physically requires lifting one
            tripod set and planting the other.

    Returns:
        ``(reward[N], new_candidate_sign[N], new_candidate_streak[N], new_confirmed_sign[N],
        new_time_since_confirmed_swap[N])``.
    """
    contact_stable = current_contact_time > debounce_s
    a = contact_stable[:, list(tripod_a_idx)].sum(dim=1).float()
    b = contact_stable[:, list(tripod_b_idx)].sum(dim=1).float()

    coherence_a = ((a == 0.0) | (a == 3.0)).float()
    coherence_b = ((b == 0.0) | (b == 3.0)).float()
    diff = a - b
    r_shape = coherence_a * coherence_b * diff.abs() / 3.0

    raw_sign = torch.sign(diff)
    raw_sign = torch.where(diff.abs() >= 2.0, raw_sign, torch.zeros_like(raw_sign))

    same_as_candidate = raw_sign == candidate_sign
    new_candidate_streak = torch.where(
        same_as_candidate, candidate_streak + dt, torch.full_like(candidate_streak, dt)
    )
    new_candidate_sign = torch.where(same_as_candidate, candidate_sign, raw_sign)

    do_confirm = (
        (new_candidate_streak >= min_swap_interval)
        & (new_candidate_sign != 0.0)
        & (new_candidate_sign != confirmed_sign)
    )
    new_confirmed_sign = torch.where(do_confirm, new_candidate_sign, confirmed_sign)
    new_time_since_swap = torch.where(
        do_confirm, torch.zeros_like(time_since_confirmed_swap), time_since_confirmed_swap + dt
    )

    anti_freeze = (new_time_since_swap <= max_hold_s).float()

    # Event-based swap credit (v4): a lump paid exactly when a dominant-set swap is confirmed,
    # scaled by the opposition quality at that step. No static configuration produces confirmed
    # swaps, so no holdable state earns anything -- and rapid genuine alternation earning more
    # credit is the target behavior, not an exploit. (The state-based support bonus and its v_z
    # gate were removed after four from-scratch failures; see the v4 addendum.)
    swap_quality = diff.abs() / 3.0
    swap_lump = swap_credit * swap_quality * do_confirm.float()

    cmd_norm = torch.norm(command_xy, dim=1)
    cmd_active = (cmd_norm > min_cmd_norm).float()

    reward = (r_shape * anti_freeze + swap_lump) * cmd_active

    return (
        reward, new_candidate_sign, new_candidate_streak, new_confirmed_sign,
        new_time_since_swap,
    )
