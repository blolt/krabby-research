"""Unit tests for the crab-hex tripod-alternation reward's pure step function (Milestone 18
Task 1 follow-on, added after ``sim_fine_tuning/2026-08-10_0058_tripod_stability/`` found no
config-only weight/param sweep moves the gait-eval harness's ``tripod_score`` metric).

Pure torch -- no Isaac Sim needed. These pin down ``crab_hex_tripod_reward.py``'s design goals:

1. The shape reward (`c_A * c_B * |a - b| / 3`) hits its 1.0 ceiling exactly when one tripod set
   is fully planted and the other fully airborne, and is 0 whenever either set is internally
   incoherent (a foot out of sync with its own tripod) or the two counts are equal.
2. A foot only counts as "in stable contact" once ``current_contact_time`` for it exceeds
   ``debounce_s`` -- a single-step-old contact reading must not move the stance count.
3. The anti-freeze gate zeroes the reward once the confirmed dominant tripod has held longer than
   ``max_hold_s`` without a new confirmed swap, so a frozen (non-alternating) stance cannot farm
   reward indefinitely -- genuine, sufficiently frequent alternation keeps the reward flowing.
4. No reward below ``min_cmd_norm`` (standing still / pure turning), matching the gating used by
   ``reward_forward_progress_along_command`` and the stride-length term.
5. The tripod-A/tripod-B foot groupings are pinned to exactly the same convention the gait-eval
   harness scores against (``gait_eval/metrics.py``'s ``FOOT_ORDER``/``TRIPOD_A``/``TRIPOD_B``).
6. (v2) The in-band stance-count support bonus: counts 3-4 earn the full ``support_scale``
   bonus, graded down to exactly 0 at count 0 (flight) and count 6 (all-down) -- so the
   unison-lunge gait that broke v1 in from-scratch training earns nothing from this term at any
   phase, while any drift toward keeping one tripod planted earns strictly increasing reward
   from the first step (support is NOT gated by the anti-freeze timer -- v1's coordination
   cliff).
"""

import sys
from pathlib import Path

import pytest
import torch

MDP_DIR = (
    Path(__file__).resolve().parents[2]
    / "parkour"
    / "parkour_tasks"
    / "parkour_tasks"
    / "crab_hexapod_task"
    / "mdp"
)
if str(MDP_DIR) not in sys.path:
    sys.path.insert(0, str(MDP_DIR))

from crab_hex_tripod_reward import (  # noqa: E402
    TRIPOD_A_IDX,
    TRIPOD_B_IDX,
    tripod_schedule_reward_step,
)

DT = 0.02

# FOOT_ORDER = (FL, FR, ML, MR, RL, RR); tripod A = {FL, MR, RL} -> indices (0, 3, 4);
# tripod B = {FR, ML, RR} -> indices (1, 2, 5).
PHASE_A_PLANTED = [999.0, 0.0, 0.0, 999.0, 999.0, 0.0]  # tripod A fully planted, B airborne
PHASE_B_PLANTED = [0.0, 999.0, 999.0, 0.0, 0.0, 999.0]  # tripod B fully planted, A airborne
ALL_PLANTED = [999.0] * 6


def _run(contact_time_seq, cmd, min_cmd_norm=0.12, debounce_s=0.08, min_swap_interval=0.1,
         max_hold_s=0.6, vz_seq=None, vz_gate_lo=0.20, vz_gate_hi=0.50, vz_ema_tau=0.5):
    """Drive the pure function across a sequence of steps for a single env.

    Args:
        contact_time_seq: list of length-6 sequences, ``current_contact_time`` per foot
            (FOOT_ORDER) at each step.
        cmd: ``(cx, cy)`` commanded planar velocity, held constant across the sequence.
        vz_seq: optional list of world-frame vertical velocities, one per step. ``None`` keeps
            the v3 stability gate bypassed (gate = 1.0, pre-v3 semantics).

    Returns:
        list of per-step reward tensors (shape ``[1]``), one per step.
    """
    candidate_sign = torch.zeros(1)
    candidate_streak = torch.zeros(1)
    confirmed_sign = torch.zeros(1)
    time_since_confirmed_swap = torch.zeros(1)
    vertical_speed_ema = torch.zeros(1) if vz_seq is not None else None
    command_xy = torch.tensor([[cmd[0], cmd[1]]], dtype=torch.float32)
    rewards = []
    for i, contact_time in enumerate(contact_time_seq):
        ct = torch.tensor([contact_time], dtype=torch.float32)
        vz = torch.tensor([vz_seq[i]], dtype=torch.float32) if vz_seq is not None else None
        (
            reward, candidate_sign, candidate_streak, confirmed_sign, time_since_confirmed_swap,
            vertical_speed_ema,
        ) = tripod_schedule_reward_step(
            ct, command_xy, candidate_sign, candidate_streak, confirmed_sign,
            time_since_confirmed_swap, DT, min_cmd_norm=min_cmd_norm, debounce_s=debounce_s,
            min_swap_interval=min_swap_interval, max_hold_s=max_hold_s,
            root_lin_vel_w_z=vz, vertical_speed_ema=vertical_speed_ema if vz_seq is not None else None,
            vz_ema_tau=vz_ema_tau, vz_gate_lo=vz_gate_lo, vz_gate_hi=vz_gate_hi,
        )
        rewards.append(reward)
    return rewards


def test_ideal_alternation_scores_near_max_mean_reward():
    """A clean, fast tripod alternation (period well under max_hold_s) should score at the
    term's ceiling of shape(1.0) + support(1.0) every step -- both tripods fully coherent and
    fully opposed (stance count pinned at 3, squarely in the support band), with alternation
    frequent enough that the anti-freeze gate never engages."""
    contact_time_seq = (([PHASE_A_PLANTED] * 6) + ([PHASE_B_PLANTED] * 6)) * 3
    rewards = _run(contact_time_seq, cmd=(1.0, 0.0))
    values = [r.item() for r in rewards]
    assert min(values) == pytest.approx(2.0, abs=1e-6)
    assert sum(values) / len(values) == pytest.approx(2.0, abs=1e-6)


def test_static_all_six_planted_scores_zero():
    """All six feet planted the whole time is internally coherent for both tripods (a=b=3) but
    not opposed at all -- must score exactly 0 throughout, not reward a non-gait 'statue'. This
    also pins the v2 support bonus's asymmetric normalization: count 6 must earn support 0
    exactly (a symmetric /3 normalization would leak +1/3 of the bonus to the all-down half of
    the unison exploit)."""
    rewards = _run([ALL_PLANTED] * 20, cmd=(1.0, 0.0))
    assert all(r.item() == pytest.approx(0.0, abs=1e-9) for r in rewards)


def test_frozen_dominant_tripod_decays_to_support_floor_past_max_hold():
    """A tripod that establishes a dominant stance and never swaps again must lose the shape
    reward once the hold timer exceeds max_hold_s, decaying from shape+support (2.0) to the
    support floor (1.0) -- NOT to zero. The support half is deliberately outside the anti-freeze
    gate (v1 gated everything, which cut off the escape path from a unison gait -- a policy
    drifting toward one-tripod-planted earned nothing until a full confirmed swap). The parked
    stance still forfeits tracking/forward-progress reward elsewhere in the config; that, not
    this term, is what makes parking a net loss."""
    rewards = _run([PHASE_A_PLANTED] * 60, cmd=(1.0, 0.0), max_hold_s=0.6)
    values = [r.item() for r in rewards]
    assert values[10] == pytest.approx(2.0, abs=1e-6)  # shape + support, within the hold window
    assert values[-1] == pytest.approx(1.0, abs=1e-6)  # support floor only, well past 0.6s
    # once the shape half decays it must stay decayed (no spurious re-arming without a real swap)
    assert all(v == pytest.approx(1.0, abs=1e-6) for v in values[45:])


def test_debounce_rejects_contact_just_below_threshold():
    """A foot's ``current_contact_time`` must exceed ``debounce_s`` to count toward its tripod's
    stance count -- a reading just under the threshold must not move it, matching the
    flicker-rejection role ``last_contact_time`` plays at liftoff in the stride-length reward.
    Below-threshold contacts read as count 0 -> support 0 too, so a brief-contact pogo gait
    earns nothing from either half of the term."""
    cmd = torch.tensor([[1.0, 0.0]])
    zero_state = torch.zeros(1)

    below = torch.tensor([[0.079, 0.0, 0.0, 0.079, 0.079, 0.0]])  # tripod A just under debounce_s
    reward_below, *_ = tripod_schedule_reward_step(
        below, cmd, zero_state, zero_state, zero_state, zero_state, DT, debounce_s=0.08,
    )
    assert reward_below.item() == pytest.approx(0.0, abs=1e-9)

    above = torch.tensor([[0.081, 0.0, 0.0, 0.081, 0.081, 0.0]])  # tripod A just over debounce_s
    reward_above, *_ = tripod_schedule_reward_step(
        above, cmd, zero_state, zero_state, zero_state, zero_state, DT, debounce_s=0.08,
    )
    assert reward_above.item() == pytest.approx(2.0, abs=1e-6)  # shape 1.0 + support 1.0 (count 3)


def test_min_cmd_norm_gates_reward_to_zero():
    """No reward for standing still or pure in-place turning, even with perfect tripod
    alternation -- matches the gating used by ``reward_forward_progress_along_command`` and the
    stride-length term."""
    contact_time_seq = (([PHASE_A_PLANTED] * 3) + ([PHASE_B_PLANTED] * 3)) * 2
    rewards = _run(contact_time_seq, cmd=(0.01, 0.0), min_cmd_norm=0.12)
    assert all(r.item() == pytest.approx(0.0, abs=1e-9) for r in rewards)


def test_reset_clears_accumulated_state():
    """After an env reset (state tensors explicitly zeroed, matching what
    ``RewardTripodSchedule.reset`` does), a fresh step must behave identically to a truly new
    env -- no leaking of the pre-reset swap history or hold timer."""
    phase1 = [PHASE_A_PLANTED] * 6
    baseline_rewards = [r.item() for r in _run(phase1, cmd=(1.0, 0.0))]

    # Drive some unrelated history (several confirmed swaps) so state is genuinely non-zero.
    # Phases must be >= 5 steps (0.1s / DT) for a candidate sign to actually get confirmed.
    contaminating_history = (([PHASE_A_PLANTED] * 6) + ([PHASE_B_PLANTED] * 6)) * 3
    candidate_sign = torch.zeros(1)
    candidate_streak = torch.zeros(1)
    confirmed_sign = torch.zeros(1)
    time_since_confirmed_swap = torch.zeros(1)
    command_xy = torch.tensor([[1.0, 0.0]])
    for contact_time in contaminating_history:
        ct = torch.tensor([contact_time], dtype=torch.float32)
        (
            _, candidate_sign, candidate_streak, confirmed_sign, time_since_confirmed_swap,
            _ema,
        ) = tripod_schedule_reward_step(
            ct, command_xy, candidate_sign, candidate_streak, confirmed_sign,
            time_since_confirmed_swap, DT,
        )
    assert confirmed_sign.item() != 0.0  # sanity: real history accumulated

    # Explicit reset -- mirrors RewardTripodSchedule.reset(env_ids).
    candidate_sign = torch.zeros(1)
    candidate_streak = torch.zeros(1)
    confirmed_sign = torch.zeros(1)
    time_since_confirmed_swap = torch.zeros(1)

    post_reset_rewards = []
    for contact_time in phase1:
        ct = torch.tensor([contact_time], dtype=torch.float32)
        (
            reward, candidate_sign, candidate_streak, confirmed_sign, time_since_confirmed_swap,
            _ema,
        ) = tripod_schedule_reward_step(
            ct, command_xy, candidate_sign, candidate_streak, confirmed_sign,
            time_since_confirmed_swap, DT,
        )
        post_reset_rewards.append(reward.item())

    assert post_reset_rewards == pytest.approx(baseline_rewards, abs=1e-6)


def test_batched_envs_are_independent():
    """One env's contact pattern/history must not influence another env's reward in the same
    batched call."""
    candidate_sign = torch.zeros(2)
    candidate_streak = torch.zeros(2)
    confirmed_sign = torch.zeros(2)
    time_since_confirmed_swap = torch.zeros(2)
    command_xy = torch.tensor([[1.0, 0.0], [1.0, 0.0]])

    rewards_env0, rewards_env1 = [], []
    for _ in range(6):
        ct = torch.tensor([PHASE_A_PLANTED, ALL_PLANTED], dtype=torch.float32)
        (
            reward, candidate_sign, candidate_streak, confirmed_sign, time_since_confirmed_swap,
            _ema,
        ) = tripod_schedule_reward_step(
            ct, command_xy, candidate_sign, candidate_streak, confirmed_sign,
            time_since_confirmed_swap, DT,
        )
        rewards_env0.append(reward[0].item())
        rewards_env1.append(reward[1].item())

    assert rewards_env0 == pytest.approx([2.0] * 6, abs=1e-6)  # shape 1.0 + support 1.0
    assert rewards_env1 == pytest.approx([0.0] * 6, abs=1e-9)  # all-six-down: shape 0, support 0


def test_tripod_index_mapping_matches_gait_eval_metrics():
    """The A/B foot groupings used by this reward must be pinned to the exact same convention the
    eval harness scores against (``gait_eval/metrics.py``'s ``FOOT_ORDER``/``TRIPOD_A``/
    ``TRIPOD_B``) -- hardcoded independently here (rather than imported, since the eval harness
    module lives under ``scripts/`` and pulls in extra dependencies) so this test is what keeps
    the two definitions honest if either ever changes."""
    foot_order = ("FL_Footpad", "FR_Footpad", "ML_Footpad", "MR_Footpad", "RL_Footpad", "RR_Footpad")
    tripod_a = ("FL_Footpad", "MR_Footpad", "RL_Footpad")
    tripod_b = ("FR_Footpad", "ML_Footpad", "RR_Footpad")
    expected_a_idx = tuple(foot_order.index(n) for n in tripod_a)
    expected_b_idx = tuple(foot_order.index(n) for n in tripod_b)
    assert TRIPOD_A_IDX == expected_a_idx
    assert TRIPOD_B_IDX == expected_b_idx


def test_batched_and_broadcastable():
    """Matches how RewardTripodSchedule calls this every step across all envs at once."""
    n_envs = 256
    current_contact_time = torch.rand(n_envs, 6, dtype=torch.float64)
    command_xy = torch.randn(n_envs, 2, dtype=torch.float64)
    candidate_sign = torch.zeros(n_envs, dtype=torch.float64)
    candidate_streak = torch.zeros(n_envs, dtype=torch.float64)
    confirmed_sign = torch.zeros(n_envs, dtype=torch.float64)
    time_since_confirmed_swap = torch.zeros(n_envs, dtype=torch.float64)

    (
        reward, new_candidate_sign, new_candidate_streak, new_confirmed_sign, new_time_since_swap,
        _new_ema,
    ) = tripod_schedule_reward_step(
        current_contact_time, command_xy, candidate_sign, candidate_streak, confirmed_sign,
        time_since_confirmed_swap, DT,
    )
    assert reward.shape == (n_envs,)
    for t in (new_candidate_sign, new_candidate_streak, new_confirmed_sign, new_time_since_swap):
        assert t.shape == (n_envs,)
        assert torch.isfinite(t).all()
    assert torch.isfinite(reward).all()
    assert (reward >= 0).all()  # bonus-dual design: never negative (the manager clips totals at 0)
    assert (reward <= 2.0).all()  # shape (<=1.0) + support (<=support_scale=1.0)


# ------------------------------------------------------------------------------------------
# v2 support-bonus tests: the unison-lunge exploit that broke v1 in from-scratch training
# ------------------------------------------------------------------------------------------

def _ramping_unison_lunge_seq(n_cycles=4, down_steps=8, flight_steps=6):
    """The gait v1's from-scratch run converged on: all six feet slam down together (contact
    times ramping realistically through the debounce window), then a full flight phase."""
    seq = []
    for _ in range(n_cycles):
        for i in range(down_steps):
            t = (i + 1) * DT  # contact time grows while planted; clears debounce_s=0.08 at step 4
            seq.append([t] * 6)
        for _ in range(flight_steps):
            seq.append([0.0] * 6)
    return seq


def test_unison_lunge_earns_nothing_and_alternation_dominates():
    """THE v1 regression test: the all-legs-together lunge gait must earn ~0 total (flight reads
    count 0 -> support 0; stable all-down reads count 6 -> support 0; a==b throughout -> shape 0;
    the only nonzero steps are the brief sub-debounce ramp moments, which cap at support 2/3),
    while an ideal alternation over the same number of steps earns close to the 2.0/step ceiling
    -- the differential is what gives training a consistent reason to prefer alternation."""
    unison = _ramping_unison_lunge_seq()
    rewards_unison = _run(unison, cmd=(1.0, 0.0))
    total_unison = sum(r.item() for r in rewards_unison)

    alternation = (([PHASE_A_PLANTED] * 7) + ([PHASE_B_PLANTED] * 7)) * 4
    rewards_alt = _run(alternation[: len(unison)], cmd=(1.0, 0.0))
    total_alt = sum(r.item() for r in rewards_alt)

    # Unison: stable all-down and flight steps are exactly 0; only the 3 sub-debounce ramp steps
    # per cycle are nonzero (counts pass 0->6 through the band), so the mean stays far below 1.
    assert total_unison / len(unison) < 0.35
    assert total_alt / len(unison) == pytest.approx(2.0, abs=1e-6)
    assert total_alt > 5 * total_unison


def test_partial_perturbation_toward_tripod_beats_pure_unison_from_step_one():
    """Pins the support-outside-anti-freeze design (v1's coordination cliff): a policy that
    merely keeps tripod A planted through the flight phase -- no confirmed swap, ever -- must
    out-earn pure unison immediately, giving the escape path a slope from the first step."""
    down_steps, flight_steps = 8, 6
    pure, partial = [], []
    for _ in range(4):
        for i in range(down_steps):
            t = (i + 1) * DT
            pure.append([t] * 6)
            partial.append([t] * 6)
        for j in range(flight_steps):
            pure.append([0.0] * 6)
            # tripod A (indices 0, 3, 4) stays planted, contact time still accumulating
            t_a = (down_steps + j + 1) * DT
            partial.append([t_a, 0.0, 0.0, t_a, t_a, 0.0])
    rewards_pure = _run(pure, cmd=(1.0, 0.0))
    rewards_partial = _run(partial, cmd=(1.0, 0.0))

    # During every flight step, partial reads count 3 (support 1.0) vs pure's count 0 (0.0).
    flight_indices = [c * (down_steps + flight_steps) + down_steps + j
                      for c in range(4) for j in range(flight_steps)]
    for idx in flight_indices:
        assert rewards_partial[idx].item() > rewards_pure[idx].item() + 0.5
    assert sum(r.item() for r in rewards_partial) > sum(r.item() for r in rewards_pure) + 5.0


def test_support_bonus_graded_counts():
    """The graded ramp at intermediate counts is the mechanism (a binary in-band indicator would
    recreate v1's flat-zero escape surface): counts 1/2/5/6 -> support 1/3, 2/3, 1/2, 0, and all
    of these are shape-incoherent or non-opposed, so the reward is the support value alone."""
    cmd = torch.tensor([[1.0, 0.0]])
    zero = torch.zeros(1)
    cases = [
        ([999.0, 0.0, 0.0, 0.0, 0.0, 0.0], 1.0 / 3.0),          # count 1 (one A foot)
        ([999.0, 0.0, 0.0, 999.0, 0.0, 0.0], 2.0 / 3.0),        # count 2 (two A feet)
        ([999.0, 999.0, 999.0, 999.0, 999.0, 0.0], 0.5),        # count 5
        ([999.0] * 6, 0.0),                                      # count 6 (all-down)
    ]
    for contact, expected in cases:
        reward, *_ = tripod_schedule_reward_step(
            torch.tensor([contact]), cmd, zero, zero, zero, zero, DT,
        )
        assert reward.item() == pytest.approx(expected, abs=1e-6), contact


def test_support_bonus_gated_by_command():
    """The support half obeys the same min_cmd_norm gate as the shape half -- an in-band stance
    while commanded to stand still earns nothing (no bonus-farming while parked at zero cmd)."""
    cmd_idle = torch.tensor([[0.01, 0.0]])
    zero = torch.zeros(1)
    in_band = torch.tensor([[999.0, 0.0, 0.0, 999.0, 999.0, 0.0]])  # count 3
    reward, *_ = tripod_schedule_reward_step(
        in_band, cmd_idle, zero, zero, zero, zero, DT, min_cmd_norm=0.12,
    )
    assert reward.item() == pytest.approx(0.0, abs=1e-9)


def test_swap_window_dip_never_negative_and_recovers():
    """A genuine tripod swap passes through a window where the total is 0 (old set lifted while
    the new set's contacts haven't cleared debounce yet -> count 0) or 6 (double stance) -- the
    reward may dip to 0 there but never goes negative (no per-swap tax, unlike a penalty form
    under the manager's zero-clip), and recovers to the full ceiling once the new set is stable
    and the swap confirms."""
    seq = [PHASE_A_PLANTED] * 7
    # A lifts, B ramping but below debounce: count 0 for 3 steps
    for i in range(3):
        t = (i + 1) * DT
        seq.append([0.0, t, t, 0.0, 0.0, t])
    # B stable from here on
    seq += [PHASE_B_PLANTED] * 10
    rewards = _run(seq, cmd=(1.0, 0.0))
    values = [r.item() for r in rewards]
    assert all(v >= -1e-9 for v in values)
    assert min(values[7:10]) == pytest.approx(0.0, abs=1e-6)  # the dip window
    assert values[-1] == pytest.approx(2.0, abs=1e-6)  # recovered: stable B + confirmed swap


def test_episode_start_all_airborne_is_exactly_zero():
    """Spawn transient (robot dropped in, no contacts registered yet): count 0 -> support 0 and
    shape 0, so the term contributes exactly nothing -- the bonus form makes the episode-start
    debounce window a non-issue rather than an unavoidable penalty."""
    rewards = _run([[0.0] * 6] * 5, cmd=(1.0, 0.0))
    assert all(r.item() == pytest.approx(0.0, abs=1e-9) for r in rewards)


# ------------------------------------------------------------------------------------------
# v3 body-stability gate tests: the tip-over-and-correct exploit that survived v2
# ------------------------------------------------------------------------------------------

ALTERNATION_36 = (([PHASE_A_PLANTED] * 6) + ([PHASE_B_PLANTED] * 6)) * 3


def test_stability_gate_open_for_level_body():
    """A level-walking body (|v_z| well under vz_gate_lo) must keep the full v2 payout --
    the flat-1 shoulder means healthy gait dynamics see zero shaping pressure from the gate."""
    rewards = _run(ALTERNATION_36, cmd=(1.0, 0.0), vz_seq=[0.10] * len(ALTERNATION_36))
    values = [r.item() for r in rewards]
    assert min(values) == pytest.approx(2.0, abs=1e-6)


def test_fresh_env_starts_gate_open():
    """EMA state starts at 0 (gate fully open): even with a violently bouncing body, the very
    first step after reset pays the full bonus -- a closed post-reset gate would bias against
    healthy exploration (the v3 implementation-trap the design review flagged)."""
    rewards = _run(ALTERNATION_36, cmd=(1.0, 0.0), vz_seq=[0.80] * len(ALTERNATION_36))
    assert rewards[0].item() == pytest.approx(2.0, abs=1e-2)


def test_stability_gate_closes_on_bouncing_body_but_shape_unaffected():
    """A bouncing body (|v_z| above vz_gate_hi once the EMA converges) must lose the support
    bonus -- but the shape (anti-phase) half is deliberately ungated, so genuine alternation
    still pays 1.0/step even while bouncing. The gate targets the support channel that the
    tip-and-correct exploit farmed, not the alternation signal itself."""
    seq = ALTERNATION_36 * 3  # 108 steps, plenty for the EMA to converge past vz_gate_hi
    rewards = _run(seq, cmd=(1.0, 0.0), vz_seq=[0.80] * len(seq))
    values = [r.item() for r in rewards]
    # EMA(0.8): exceeds hi=0.50 after ~24 steps (alpha=0.04); late steps are shape-only.
    assert values[-1] == pytest.approx(1.0, abs=1e-3)
    assert min(values[40:]) == pytest.approx(1.0, abs=1e-3)
    # early steps still paid the full bonus while the EMA was low
    assert values[0] == pytest.approx(2.0, abs=1e-2)


def test_stability_gate_graded_between_thresholds():
    """The ramp is linear between lo and hi: a body hovering at EMA ~0.35 (gap midpoint) keeps
    ~half the support bonus -- an escape slope for exploits, not a binary cliff."""
    seq = ALTERNATION_36 * 5  # 180 steps for tight EMA convergence to 0.35
    rewards = _run(seq, cmd=(1.0, 0.0), vz_seq=[0.35] * len(seq))
    # gate -> (0.50 - 0.35) / 0.30 = 0.5; reward -> shape 1.0 + support 0.5
    assert rewards[-1].item() == pytest.approx(1.5, abs=2e-2)


def test_stability_gate_reopens_when_bouncing_stops():
    """The EMA decays once the body levels out -- the gate is a running assessment, not a
    latched punishment; a policy that stops bouncing gets its bonus back within ~tau seconds."""
    n_bounce, n_calm = 48, 132
    seq = ALTERNATION_36 * 5
    vz = [0.80] * n_bounce + [0.0] * n_calm
    rewards = _run(seq[: len(vz)], cmd=(1.0, 0.0), vz_seq=vz)
    values = [r.item() for r in rewards]
    assert min(values[40:n_bounce]) == pytest.approx(1.0, abs=1e-2)  # gate closed while bouncing
    assert values[-1] == pytest.approx(2.0, abs=1e-2)  # fully reopened after calming


def test_unison_lunge_with_realistic_vz_earns_less_than_without():
    """The v2-exploit regression test, upgraded: the unison lunge's band-transit crumbs (the
    only nonzero steps v2 left it) shrink further once its own vertical bouncing closes the
    gate. The gate must only ever reduce the exploit's take, never increase it."""
    unison = _ramping_unison_lunge_seq()
    # Bouncing profile: high |v_z| during the slam-down and flight transitions.
    vz = ([0.6] * 8 + [0.7] * 6) * 4
    r_without = sum(r.item() for r in _run(unison, cmd=(1.0, 0.0)))
    r_with = sum(r.item() for r in _run(unison, cmd=(1.0, 0.0), vz_seq=vz[: len(unison)]))
    assert r_with <= r_without + 1e-6
    assert r_with / len(unison) < 0.2
