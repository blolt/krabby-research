"""Offline replay gate for the camshaft direction-reversal penalty (mandatory before the
weight screens; sibling of 2026-08-10_0058_tripod_stability/offline_replay/replay_gate.py).

Replays the exact ``PenaltyMotorDirectionReversal`` rule (sticky-sign, deadzone 0.05 —
cross-checked against ``gait_eval.metrics._sticky_sign_reversals``, a byte-for-byte match)
over saved gait-eval npz traces and reports weighted income per minute of steady walking.

Fixtures:
  (a) DEGENERATE: the velocity-era from-scratch oscillator (all six shafts sweeping at
      ~1.4 Hz, one-direction ratio 0.006) — the penalty must price this heavily;
  (b) HEALTHY (synthetic): constant one-direction spin at CAM_VEL_SCALE with brief
      deadzone dwells — must pay ~0;
  (c) REFERENCE-BEHAVIOR: the position-era symmetric reference traces — contextualizes
      what the adopted gait would have paid (its shafts oscillated by design back then,
      so this quantifies the pressure the term will exert against old habits).

Gate criteria (proportionality; reward-income scale from the velact from-scratch canary,
~21 mean reward over ~19.5 s episodes ≈ 65/min):
  (1) degenerate penalty magnitude >= 3% of locomotion income at the candidate weight
      (meaningful pressure), and
  (2) degenerate penalty magnitude <= 15% of locomotion income (cannot dominate), and
  (3) synthetic healthy trace pays <= 5% of the degenerate trace's penalty.
Usage: python replay_reversal_gate.py     (exit 0 = at least one candidate weight passes)
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO = Path("/home/nickmagus/krabby/krabby-research")
SHAFT_IDS = [1, 3, 5, 7, 9, 11]  # articulation order (print_joint_order.py ground truth)
VEL_DEADZONE = 0.05  # PenaltyMotorDirectionReversal default
DT_FALLBACK = 0.02
# Round 2 (2026-08-13, user-approved escalation after -0.1/-0.3 were absorbed): the 15%
# proportionality cap is deliberately waived — the screens showed even 9.9% of income
# produces zero dose-response on reversal rate, so these weights intentionally dominate.
CANDIDATE_WEIGHTS = [-0.6, -1.0]
LOCOMOTION_INCOME_PER_MIN = 65.0  # velact from-scratch: ~21 reward / ~19.5 s episode

FIXTURES = {
    "degen_velact_oscillator": REPO
    / "parkour/logs/rsl_rl/gait_eval/v1/flat_walk_forward/seed001/2026-08-13_23-22-03/raw",
    "reference_position_era": REPO
    / "sim_fine_tuning/2026-08-13_0035_mirror_symmetry/fromscratch_sym_20k/gait_eval_final"
    / "flat_walk_forward/seed001/2026-08-13_10-54-18/raw",
}


def sticky_reversals(jv: np.ndarray, deadzone: float) -> np.ndarray:
    """Per-step reversal count summed over shafts — the exact reward-term rule."""
    prev = np.zeros(jv.shape[1])
    per_step = np.zeros(jv.shape[0])
    for t in range(jv.shape[0]):
        cur = np.sign(jv[t]) * (np.abs(jv[t]) > deadzone)
        per_step[t] = ((prev * cur) < 0).sum()
        nonzero = cur != 0
        prev = np.where(nonzero, cur, prev)
    return per_step


def income_per_min(raw_dir: Path) -> tuple[float, float]:
    """Return (unweighted reversal income per steady minute, steady minutes)."""
    total, steady_s = 0.0, 0.0
    files = sorted(raw_dir.glob("episode_*.npz"))
    if not files:
        raise FileNotFoundError(f"no episode npz under {raw_dir}")
    for f in files:
        d = np.load(f)
        jv = np.asarray(d["joint_vel"], dtype=np.float64)[:, SHAFT_IDS]
        dt = float(d["dt"]) if "dt" in d else DT_FALLBACK
        per_step = sticky_reversals(jv, VEL_DEADZONE)
        steady = (
            np.asarray(d["steady_mask"], dtype=bool)
            if "steady_mask" in d
            else np.ones(len(per_step), dtype=bool)
        )
        n = min(len(per_step), len(steady))
        # reward manager applies weight * term * dt per step; weight applied by caller
        total += float((per_step[:n] * steady[:n]).sum()) * dt
        steady_s += float(steady[:n].sum()) * dt
    return (total / max(steady_s / 60.0, 1e-9), steady_s / 60.0)


def synthetic_healthy(n_steps: int = 2925, dt: float = DT_FALLBACK) -> float:
    """Constant one-direction spin at 6 rad/s with periodic deadzone dwells; returns
    unweighted income/min (should be ~0)."""
    jv = np.full((n_steps, len(SHAFT_IDS)), 6.0)
    jv[::100] = 0.01  # brief dwell inside the deadzone — sticky rule must not charge
    per_step = sticky_reversals(jv, VEL_DEADZONE)
    return float(per_step.sum()) * dt / (n_steps * dt / 60.0)


def main() -> int:
    print("=== Camshaft direction-reversal penalty: offline replay gate ===")
    incomes: dict[str, float] = {}
    for name, raw_dir in FIXTURES.items():
        inc, minutes = income_per_min(raw_dir)
        incomes[name] = inc
        print(f"[{name}] unweighted income = {inc:.1f} rev*dt/min over {minutes:.2f} steady min")
    incomes["healthy_synthetic"] = synthetic_healthy()
    print(f"[healthy_synthetic] unweighted income = {incomes['healthy_synthetic']:.3f} rev*dt/min")

    degen = incomes["degen_velact_oscillator"]
    healthy = incomes["healthy_synthetic"]
    any_pass = False
    for w in CANDIDATE_WEIGHTS:
        pen = abs(w) * degen
        frac = pen / LOCOMOTION_INCOME_PER_MIN
        healthy_frac = (abs(w) * healthy) / max(pen, 1e-9)
        ok = 0.03 <= frac <= 0.15 and healthy_frac <= 0.05
        any_pass = any_pass or ok
        print(
            f"weight {w:+.2f}: degen penalty {pen:.2f}/min = {frac * 100:.1f}% of locomotion "
            f"income; healthy pays {healthy_frac * 100:.2f}% of degen -> "
            f"{'PASS' if ok else 'FAIL'}"
        )
        ref_pen = abs(w) * incomes["reference_position_era"]
        print(
            f"  (context: position-era reference gait would have paid {ref_pen:.2f}/min "
            f"= {ref_pen / LOCOMOTION_INCOME_PER_MIN * 100:.1f}% of income)"
        )

    print("GATE:", "PASS" if any_pass else "FAIL")
    return 0 if any_pass else 1


if __name__ == "__main__":
    sys.exit(main())
