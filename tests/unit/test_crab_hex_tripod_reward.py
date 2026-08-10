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


def _run(contact_time_seq, cmd, min_cmd_norm=0.12, debounce_s=0.08, min_swap_interval=0.1, max_hold_s=0.6):
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
            min_swap_interval=min_swap_interval, max_hold_s=max_hold_s,
        )
        rewards.append(reward)
    return rewards


def test_ideal_alternation_scores_near_max_mean_reward():
    """A clean, fast tripod alternation (period well under max_hold_s) should score at the shape
    reward's ceiling of 1.0 every step -- both tripods fully coherent and fully opposed, with
    alternation frequent enough that the anti-freeze gate never engages."""
    contact_time_seq = (([PHASE_A_PLANTED] * 6) + ([PHASE_B_PLANTED] * 6)) * 3
    rewards = _run(contact_time_seq, cmd=(1.0, 0.0))
    values = [r.item() for r in rewards]
    assert min(values) == pytest.approx(1.0, abs=1e-6)
    assert sum(values) / len(values) == pytest.approx(1.0, abs=1e-6)


def test_static_all_six_planted_scores_zero():
    """All six feet planted the whole time is internally coherent for both tripods (a=b=3) but
    not opposed at all -- must score exactly 0 throughout, not reward a non-gait 'statue'."""
    rewards = _run([ALL_PLANTED] * 20, cmd=(1.0, 0.0))
    assert all(r.item() == pytest.approx(0.0, abs=1e-9) for r in rewards)


def test_frozen_dominant_tripod_decays_to_zero_past_max_hold():
    """A tripod that establishes a dominant stance and never swaps again must keep paying out
    while within max_hold_s of the confirmed swap, then decay to exactly 0 once the hold timer
    exceeds it -- this is what forces genuine alternation instead of a static (if coherent)
    stance."""
    rewards = _run([PHASE_A_PLANTED] * 60, cmd=(1.0, 0.0), max_hold_s=0.6)
    values = [r.item() for r in rewards]
    assert values[10] == pytest.approx(1.0, abs=1e-6)  # well within the hold window
    assert values[-1] == pytest.approx(0.0, abs=1e-9)  # 60 steps * 0.02s = 1.2s, well past 0.6s
    # once it decays it must stay decayed (no spurious re-arming without a real swap)
    assert all(v == pytest.approx(0.0, abs=1e-9) for v in values[45:])


def test_debounce_rejects_contact_just_below_threshold():
    """A foot's ``current_contact_time`` must exceed ``debounce_s`` to count toward its tripod's
    stance count -- a reading just under the threshold must not move it, matching the
    flicker-rejection role ``last_contact_time`` plays at liftoff in the stride-length reward."""
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
    assert reward_above.item() == pytest.approx(1.0, abs=1e-6)


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
        ) = tripod_schedule_reward_step(
            ct, command_xy, candidate_sign, candidate_streak, confirmed_sign,
            time_since_confirmed_swap, DT,
        )
        rewards_env0.append(reward[0].item())
        rewards_env1.append(reward[1].item())

    assert rewards_env0 == pytest.approx([1.0] * 6, abs=1e-6)
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
    ) = tripod_schedule_reward_step(
        current_contact_time, command_xy, candidate_sign, candidate_streak, confirmed_sign,
        time_since_confirmed_swap, DT,
    )
    assert reward.shape == (n_envs,)
    for t in (new_candidate_sign, new_candidate_streak, new_confirmed_sign, new_time_since_swap):
        assert t.shape == (n_envs,)
        assert torch.isfinite(t).all()
    assert torch.isfinite(reward).all()
    assert (reward >= 0).all()
    assert (reward <= 1.0).all()
