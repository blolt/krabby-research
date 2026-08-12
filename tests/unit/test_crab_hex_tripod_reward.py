"""Unit tests for the crab-hex tripod-alternation reward's pure step function (Milestone 18
Task 1 follow-on; see ``sim_fine_tuning/2026-08-10_0058_tripod_stability/RESULTS.md`` for the
v1-v4 design history these tests pin down).

Pure torch -- no Isaac Sim needed. Design goals under test:

1. The shape reward (`c_A * c_B * |a - b| / 3`) hits its 1.0 ceiling exactly when one tripod set
   is fully planted and the other fully airborne, and is 0 whenever either set is internally
   incoherent (a foot out of sync with its own tripod) or the two counts are equal.
2. A foot only counts as "in stable contact" once ``current_contact_time`` for it exceeds
   ``debounce_s`` -- a single-step-old contact reading must not move the stance count.
3. The anti-freeze gate zeroes the shape reward once the confirmed dominant tripod has held
   longer than ``max_hold_s`` without a new confirmed swap.
4. No reward below ``min_cmd_norm`` (standing still / pure turning), matching the gating used by
   ``reward_forward_progress_along_command`` and the stride-length term.
5. The tripod-A/tripod-B foot groupings are pinned to exactly the same convention the gait-eval
   harness scores against (``gait_eval/metrics.py``'s ``FOOT_ORDER``/``TRIPOD_A``/``TRIPOD_B``).
6. (v4) Income is EVENT-based: a ``swap_credit`` lump is paid exactly on the step a dominant-set
   swap is confirmed, scaled by the opposition quality ``|a - b| / 3`` at that step. Four
   from-scratch failures (v1 lunge, v2 tip-rock, v3 skate, v3b drag) showed every state-paying
   channel gets farmed by a cheap state-holding gait -- so v4 removed the support bonus and its
   v_z gate entirely, and NO static contact configuration may earn ongoing income.
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
SWAP_CREDIT = 15.0

# FOOT_ORDER = (FL, FR, ML, MR, RL, RR); tripod A = {FL, MR, RL} -> indices (0, 3, 4);
# tripod B = {FR, ML, RR} -> indices (1, 2, 5).
PHASE_A_PLANTED = [999.0, 0.0, 0.0, 999.0, 999.0, 0.0]  # tripod A fully planted, B airborne
PHASE_B_PLANTED = [0.0, 999.0, 999.0, 0.0, 0.0, 999.0]  # tripod B fully planted, A airborne
ALL_PLANTED = [999.0] * 6

# 6-step phases (0.12s) alternate faster than max_hold_s=0.6; each phase confirms exactly one
# swap (min_swap_interval=0.1s = 5 steps at DT=0.02).
ALTERNATION_36 = (([PHASE_A_PLANTED] * 6) + ([PHASE_B_PLANTED] * 6)) * 3


def _run(contact_time_seq, cmd, min_cmd_norm=0.12, debounce_s=0.08, min_swap_interval=0.1,
         max_hold_s=0.6, swap_credit=SWAP_CREDIT):
    """Drive the pure function across a sequence of steps for a single env.

    Args:
        contact_time_seq: list of length-6 sequences, ``current_contact_time`` per foot
            (FOOT_ORDER) at each step.
        cmd: ``(cx, cy)`` commanded planar velocity, held constant across the sequence.

    Returns:
        list of per-step reward tensors (shape ``[1]``), one per step.
    """
    candidate_sign = torch.zeros(1)
    candidate_streak = torch.zeros(1)
    confirmed_sign = torch.zeros(1)
    time_since_confirmed_swap = torch.zeros(1)
    command_xy = torch.tensor([[cmd[0], cmd[1]]], dtype=torch.float32)
    rewards = []
    for contact_time in contact_time_seq:
        ct = torch.tensor([contact_time], dtype=torch.float32)
        (
            reward, candidate_sign, candidate_streak, confirmed_sign, time_since_confirmed_swap,
        ) = tripod_schedule_reward_step(
            ct, command_xy, candidate_sign, candidate_streak, confirmed_sign,
            time_since_confirmed_swap, DT, min_cmd_norm=min_cmd_norm, debounce_s=debounce_s,
            min_swap_interval=min_swap_interval, max_hold_s=max_hold_s, swap_credit=swap_credit,
        )
        rewards.append(reward)
    return rewards


def test_ideal_alternation_earns_shape_plus_one_lump_per_phase():
    """Clean tripod alternation: the shape channel pays 1.0 every step (coherent, opposed,
    anti-freeze never trips), and each phase confirms exactly one swap -> one swap_credit lump,
    quality 1.0. With 6-step phases that's mean = 1.0 + swap_credit/6 per step."""
    rewards = _run(ALTERNATION_36, cmd=(1.0, 0.0))
    values = [r.item() for r in rewards]
    assert min(values) == pytest.approx(1.0, abs=1e-6)  # non-lump steps: pure shape
    assert max(values) == pytest.approx(1.0 + SWAP_CREDIT, abs=1e-6)  # lump steps
    n_lumps = sum(1 for v in values if v > 10.0)
    assert n_lumps == 6  # one confirmed swap per 6-step phase, 6 phases
    assert sum(values) / len(values) == pytest.approx(1.0 + SWAP_CREDIT / 6.0, abs=1e-6)


def test_static_all_six_planted_scores_zero():
    """All six feet planted forever: a=b=3 (no opposition, no dominant sign, no swaps) -- must
    score exactly 0 throughout. Statues earn nothing."""
    rewards = _run([ALL_PLANTED] * 40, cmd=(1.0, 0.0))
    assert all(r.item() == pytest.approx(0.0, abs=1e-9) for r in rewards)


def test_no_static_state_earns_ongoing_income():
    """THE v4 design pin, distilled from four from-scratch failures: no holdable contact
    configuration may produce ongoing income. Every static pattern's late-window (last 40 steps
    of 80) sum must be exactly 0 -- any early income (initial shape window, at most one confirm
    lump) must dry up."""
    static_patterns = [
        ALL_PLANTED,                                     # statue (v2's all-down half)
        [0.0] * 6,                                       # flight (v1's airborne half)
        [999.0, 0.0, 0.0, 0.0, 0.0, 0.0],                # count 1
        [999.0, 0.0, 0.0, 999.0, 0.0, 0.0],              # count 2
        [999.0, 999.0, 999.0, 999.0, 999.0, 0.0],        # count 5
        PHASE_A_PLANTED,                                 # frozen single tripod (never swaps)
    ]
    for pattern in static_patterns:
        rewards = _run([pattern] * 80, cmd=(1.0, 0.0))
        late = sum(r.item() for r in rewards[40:])
        assert late == pytest.approx(0.0, abs=1e-9), pattern


def test_frozen_dominant_tripod_decays_to_zero_past_max_hold():
    """A tripod that establishes a dominant stance and never swaps: shape pays only within the
    anti-freeze window, the single initial confirm pays one lump, and then income goes to
    exactly 0 -- there is no support floor in v4 (v2/v3's floor is what every degenerate gait
    farmed)."""
    rewards = _run([PHASE_A_PLANTED] * 60, cmd=(1.0, 0.0), max_hold_s=0.6)
    values = [r.item() for r in rewards]
    n_lumps = sum(1 for v in values if v > 10.0)
    assert n_lumps == 1  # the initial confirm, never another
    assert values[10] == pytest.approx(1.0, abs=1e-6)  # shape only, within the hold window
    assert values[-1] == pytest.approx(0.0, abs=1e-9)  # past max_hold: nothing
    assert all(v == pytest.approx(0.0, abs=1e-9) for v in values[45:])


def test_swap_quality_scales_the_lump():
    """A sloppy swap (|a-b| = 2 at confirmation, e.g. one foot of the 'airborne' set still down)
    earns 2/3 of the credit; the shape channel pays 0 there (incoherent set). Grading keeps a
    slope toward cleaner swaps."""
    sloppy_a = [999.0, 999.0, 0.0, 999.0, 999.0, 0.0]  # a=3, b=1 -> diff +2
    sloppy_b = [0.0, 999.0, 999.0, 0.0, 999.0, 999.0]  # a=1, b=3 -> diff -2
    seq = ([sloppy_a] * 7) + ([sloppy_b] * 7)
    rewards = _run(seq, cmd=(1.0, 0.0))
    values = [r.item() for r in rewards]
    lumps = [v for v in values if v > 1.0]
    assert len(lumps) == 2
    for lump in lumps:
        assert lump == pytest.approx(SWAP_CREDIT * 2.0 / 3.0, abs=1e-5)
    # non-lump steps: r_shape = 0 (one set incoherent), no state income
    assert all(v == pytest.approx(0.0, abs=1e-9) for v in values if v <= 1.0)


def test_debounce_rejects_contact_just_below_threshold():
    """A foot's ``current_contact_time`` must exceed ``debounce_s`` to count toward its tripod's
    stance count -- a reading just under the threshold must not move it."""
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
    # single step from zero state: shape pays 1.0; no confirm yet (streak 0.02 < 0.1), no lump
    assert reward_above.item() == pytest.approx(1.0, abs=1e-6)


def test_min_cmd_norm_gates_everything_to_zero():
    """No income for alternating in place while commanded to stand still -- both the shape
    channel and the swap lumps obey the command gate."""
    rewards = _run(ALTERNATION_36, cmd=(0.01, 0.0), min_cmd_norm=0.12)
    assert all(r.item() == pytest.approx(0.0, abs=1e-9) for r in rewards)


def test_unison_lunge_earns_exactly_nothing():
    """The v1/v2 exploit family: all six legs slamming down together then going airborne
    together. a == b at every step -> no opposition, no dominant sign, no swaps, no shape --
    total income exactly 0 (v2's support paid band-transit crumbs here; v4 pays nothing)."""
    seq = []
    for _ in range(4):
        for i in range(8):
            seq.append([(i + 1) * DT] * 6)  # contact times ramping through debounce together
        for _ in range(6):
            seq.append([0.0] * 6)  # flight
    rewards = _run(seq, cmd=(1.0, 0.0))
    assert sum(r.item() for r in rewards) == pytest.approx(0.0, abs=1e-9)


def test_partial_perturbation_toward_tripod_beats_pure_unison():
    """The escape-slope pin (v1's coordination-cliff lesson): a policy that merely keeps tripod
    A planted through the flight phase -- no full alternation yet -- immediately earns shape
    income during the (3,0) windows (anti-freeze starts open) plus one confirm lump, while pure
    unison earns exactly 0. The first steps toward tripod structure must pay."""
    down_steps, flight_steps = 8, 6
    pure, partial = [], []
    for _ in range(4):
        for i in range(down_steps):
            t = (i + 1) * DT
            pure.append([t] * 6)
            partial.append([t] * 6)
        for j in range(flight_steps):
            pure.append([0.0] * 6)
            t_a = (down_steps + j + 1) * DT
            partial.append([t_a, 0.0, 0.0, t_a, t_a, 0.0])  # tripod A stays planted
    r_pure = sum(r.item() for r in _run(pure, cmd=(1.0, 0.0)))
    r_partial = sum(r.item() for r in _run(partial, cmd=(1.0, 0.0)))
    assert r_pure == pytest.approx(0.0, abs=1e-9)
    assert r_partial > 3.0  # shape window income + a confirm lump


def test_swap_window_dip_never_negative_and_pays_on_completion():
    """A genuine tripod swap passes through a sub-debounce window (old set lifted, new set not
    yet stable -> counts (0,0)): reward may dip to 0 there but never negative, and completing
    the swap pays the confirm lump once the new set stabilizes and persists."""
    seq = [PHASE_A_PLANTED] * 7
    for i in range(3):
        t = (i + 1) * DT
        seq.append([0.0, t, t, 0.0, 0.0, t])  # B ramping, below debounce: count 0
    seq += [PHASE_B_PLANTED] * 10
    rewards = _run(seq, cmd=(1.0, 0.0))
    values = [r.item() for r in rewards]
    assert all(v >= -1e-9 for v in values)
    assert min(values[7:10]) == pytest.approx(0.0, abs=1e-6)  # the dip window
    n_lumps = sum(1 for v in values if v > 10.0)
    assert n_lumps == 2  # initial A confirm + the A->B swap
    assert values[-1] == pytest.approx(1.0, abs=1e-6)  # stable B: shape income resumed


def test_episode_start_all_airborne_is_exactly_zero():
    """Spawn transient (no contacts registered yet): no counts, no swaps -> exactly 0."""
    rewards = _run([[0.0] * 6] * 5, cmd=(1.0, 0.0))
    assert all(r.item() == pytest.approx(0.0, abs=1e-9) for r in rewards)


def test_reset_clears_accumulated_state():
    """After an env reset (state tensors explicitly zeroed, matching RewardTripodSchedule.reset),
    a fresh run must behave identically to a truly new env -- no leaking of swap history."""
    phase1 = [PHASE_A_PLANTED] * 6
    baseline_rewards = [r.item() for r in _run(phase1, cmd=(1.0, 0.0))]

    # Drive real history (several confirmed swaps) so state is genuinely non-zero.
    candidate_sign = torch.zeros(1)
    candidate_streak = torch.zeros(1)
    confirmed_sign = torch.zeros(1)
    time_since_confirmed_swap = torch.zeros(1)
    command_xy = torch.tensor([[1.0, 0.0]])
    for contact_time in ALTERNATION_36:
        ct = torch.tensor([contact_time], dtype=torch.float32)
        (
            _, candidate_sign, candidate_streak, confirmed_sign, time_since_confirmed_swap,
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

    post_reset = []
    for contact_time in phase1:
        ct = torch.tensor([contact_time], dtype=torch.float32)
        (
            reward, candidate_sign, candidate_streak, confirmed_sign, time_since_confirmed_swap,
        ) = tripod_schedule_reward_step(
            ct, command_xy, candidate_sign, candidate_streak, confirmed_sign,
            time_since_confirmed_swap, DT,
        )
        post_reset.append(reward.item())

    assert post_reset == pytest.approx(baseline_rewards, abs=1e-6)


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
        ) = tripod_schedule_reward_step(
            ct, command_xy, candidate_sign, candidate_streak, confirmed_sign,
            time_since_confirmed_swap, DT,
        )
        rewards_env0.append(reward[0].item())
        rewards_env1.append(reward[1].item())

    # env0: shape 1.0/step + exactly one initial confirm lump (index depends on float32
    # accumulation of the 0.1s streak -- step 4 or 5)
    lump_indices = [i for i, v in enumerate(rewards_env0) if v > 10.0]
    assert len(lump_indices) == 1
    assert rewards_env0[lump_indices[0]] == pytest.approx(1.0 + SWAP_CREDIT, abs=1e-6)
    assert [v for i, v in enumerate(rewards_env0) if i != lump_indices[0]] == pytest.approx([1.0] * 5, abs=1e-6)
    # env1: statue earns nothing, and env0's lump must not leak into it
    assert rewards_env1 == pytest.approx([0.0] * 6, abs=1e-9)


def test_tripod_index_mapping_matches_gait_eval_metrics():
    """The A/B foot groupings used by this reward must be pinned to the exact same convention the
    eval harness scores against (``gait_eval/metrics.py``'s ``FOOT_ORDER``/``TRIPOD_A``/
    ``TRIPOD_B``) -- hardcoded independently here (rather than imported, since the eval harness
    module lives under ``scripts/`` and pulls in extra dependencies) so this test is what keeps
    the two definitions honest if either ever changes."""
    foot_order = ("FL_Footpad", "FR_Footpad", "ML_Footpad", "MR_Footpad", "RL_Footpad", "RR_Footpad")
    tripod_a = ("FL_Footpad", "MR_Footpad", "RL_Footpad")
    tripod_b = ("FR_Footpad", "ML_Footpad", "RR_Footpad")
    assert TRIPOD_A_IDX == tuple(foot_order.index(n) for n in tripod_a)
    assert TRIPOD_B_IDX == tuple(foot_order.index(n) for n in tripod_b)


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
    ) = tripod_schedule_reward_step(
        current_contact_time, command_xy, candidate_sign, candidate_streak, confirmed_sign,
        time_since_confirmed_swap, DT,
    )
    assert reward.shape == (n_envs,)
    for t in (new_candidate_sign, new_candidate_streak, new_confirmed_sign, new_time_since_swap):
        assert t.shape == (n_envs,)
        assert torch.isfinite(t).all()
    assert torch.isfinite(reward).all()
    assert (reward >= 0).all()  # never negative (the manager clips totals at 0)
    assert (reward <= 1.0 + SWAP_CREDIT).all()  # shape (<=1.0) + one lump max per step
