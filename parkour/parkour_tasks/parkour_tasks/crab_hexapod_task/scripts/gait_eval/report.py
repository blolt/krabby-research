# SPDX-License-Identifier: BSD-3-Clause
"""Scoring orchestration and report writing for the crab-hex gait eval harness.

Pure -- takes the harness's logged numpy arrays and turns them into per-episode / per-scenario
metrics, JSON files, a human-readable summary, and an optional JSONL history entry. No Isaac Sim,
so the whole scoring path is exercisable offline against a saved NPZ.

History mirrors ``parkour/scripts/curriculum_metrics.py`` (which trends *training* metrics) so a
tripod score can be trended across checkpoints with the same muscle memory, but the two are
deliberately separate: that one parses training stdout, this one measures play-time gait.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from gait_eval import metrics as M
from gait_eval.schedule import CompiledSchedule, Scenario


def _window_mask(
    *,
    segment_id: np.ndarray,
    steady: np.ndarray,
    hold_idx: int,
    n_steps: int,
    fall_trim_steps: int,
    ended_in_fall: bool,
) -> np.ndarray:
    """Steps of one hold that are eligible for scoring, for a single env."""
    total = segment_id.shape[0]
    valid = np.zeros(total, dtype=bool)
    upper = min(n_steps, total)
    if ended_in_fall:
        # The last half-second before a fall is a fall, not a gait sample.
        upper = max(0, upper - fall_trim_steps)
    valid[:upper] = True
    return valid & (segment_id == hold_idx) & steady


def score_episode(
    raw: dict[str, np.ndarray],
    *,
    env_idx: int,
    compiled: CompiledSchedule,
    scenario: Scenario,
    dt: float,
    term_reason: str,
    n_steps: int,
    action_groups: dict[str, list[int]] | None = None,
    joint_vel_groups: dict[str, list[int]] | None = None,
) -> dict:
    """All derived metrics for one episode, per hold plus an episode roll-up."""
    threshold = float(scenario.get_default("contact_force_threshold"))
    min_window_steps = max(1, int(round(float(scenario.get_default("min_window_s")) / dt)))
    fall_trim = int(round(float(scenario.get_default("fall_exclusion_s")) / dt))
    min_cycles = int(scenario.get_default("min_cycles"))
    slip_thresh = float(scenario.get_default("slip_speed_threshold"))
    ended_in_fall = term_reason in ("fall", "hard_fall")

    contact_all = raw["foot_force_norm"][:, env_idx, :] > threshold
    segment_id = compiled.segment_id[:, env_idx]
    steady = compiled.steady_mask[:, env_idx]

    out: dict[str, Any] = {
        "env_index": env_idx,
        "termination_reason": term_reason,
        "n_steps": int(n_steps),
        "duration_s": float(n_steps * dt),
        "completed_schedule": bool(term_reason == "schedule_complete"),
        "contact_force_threshold": threshold,
        "holds": {},
    }

    scored, weights, discarded = [], [], []
    for hold_idx, label in enumerate(compiled.hold_labels):
        mask = _window_mask(
            segment_id=segment_id,
            steady=steady,
            hold_idx=hold_idx,
            n_steps=n_steps,
            fall_trim_steps=fall_trim,
            ended_in_fall=ended_in_fall,
        )
        idx = np.flatnonzero(mask)
        contact = contact_all[idx]
        tri = M.tripod_window_metrics(
            contact, dt=dt, min_window_steps=min_window_steps, min_cycles=min_cycles
        )
        entry: dict[str, Any] = {"label": label, "tripod": tri, "n_steps": int(idx.size)}

        if tri["valid"]:
            entry["air_time"] = M.air_time_metrics(contact, dt=dt)
            entry["tracking"] = M.tracking_metrics(
                raw["cmd_applied"][idx, env_idx, :],
                raw["root_lin_vel_b"][idx, env_idx, :],
                raw["root_ang_vel_b"][idx, env_idx, :],
            )
            entry["slip"] = M.slip_metrics(
                contact,
                raw["foot_pos_w"][idx, env_idx],
                raw["foot_lin_vel_w"][idx, env_idx],
                dt=dt,
                foot_force_norm=raw["foot_force_norm"][idx, env_idx],
                foot_ang_vel_w=raw["foot_ang_vel_w"][idx, env_idx],
                slip_speed_threshold=slip_thresh,
            )
            if not tri["low_confidence"]:
                scored.append(tri["tripod_score"])
                weights.append(int(idx.size))
        else:
            discarded.append({"label": label, "reason": tri["discard_reason"], "n_steps": int(idx.size)})
        out["holds"][label] = entry

    # Episode-level metrics use every logged step, not just steady windows -- orientation and action
    # smoothness are episode properties, and clipping them to holds would hide transients.
    ep = slice(0, max(1, n_steps))
    ep_contact = contact_all[ep]
    yaw = M.yaw_from_quat_wxyz(raw["root_quat_w"][ep, env_idx, :])
    out["air_time_episode"] = M.air_time_metrics(ep_contact, dt=dt)
    out["stride"] = M.stride_metrics(
        ep_contact,
        raw["foot_pos_w"][ep, env_idx],
        dt=dt,
        cmd_xy=raw["cmd_applied"][ep, env_idx, :2],
        root_yaw=yaw,
    )
    out["swing_clearance"] = M.swing_clearance_metrics(
        ep_contact, raw["foot_pos_w"][ep, env_idx], raw["terrain_z"][ep, env_idx]
    )
    out["slip_episode"] = M.slip_metrics(
        ep_contact,
        raw["foot_pos_w"][ep, env_idx],
        raw["foot_lin_vel_w"][ep, env_idx],
        dt=dt,
        foot_force_norm=raw["foot_force_norm"][ep, env_idx],
        foot_ang_vel_w=raw["foot_ang_vel_w"][ep, env_idx],
        slip_speed_threshold=slip_thresh,
    )
    out["orientation"] = M.orientation_metrics(raw["root_quat_w"][ep, env_idx, :])
    out["actions"] = M.action_metrics(
        raw["actions"][ep, env_idx],
        joint_groups=action_groups,
        joint_vel=raw["joint_vel"][ep, env_idx],
        joint_vel_groups=joint_vel_groups,
    )

    out["discarded_windows"] = discarded
    if scored:
        w = np.asarray(weights, dtype=np.float64)
        out["tripod_score"] = float(np.average(np.asarray(scored, dtype=np.float64), weights=w))
    else:
        # Explicitly null, never 0.0: "not measurable" and "measured and bad" need different fixes.
        out["tripod_score"] = None
    out["tippy_tap_fraction"] = out["air_time_episode"].get("tippy_tap_fraction")
    out["slip_ratio_mean"] = out["slip_episode"]["pooled_slip_ratio"]["mean"]
    return out


def score_run(
    raw: dict[str, np.ndarray],
    *,
    compiled: CompiledSchedule,
    scenario: Scenario,
    dt: float,
    term_reason: list[str],
    n_steps_env: list[int],
    action_groups: dict[str, list[int]] | None = None,
    joint_vel_groups: dict[str, list[int]] | None = None,
) -> list[dict]:
    return [
        score_episode(
            raw,
            env_idx=i,
            compiled=compiled,
            scenario=scenario,
            dt=dt,
            term_reason=term_reason[i],
            n_steps=n_steps_env[i],
            action_groups=action_groups,
            joint_vel_groups=joint_vel_groups,
        )
        for i in range(len(term_reason))
    ]


def aggregate(episodes: list[dict]) -> dict:
    """Scenario-level roll-up.

    Headline is the **median** tripod score across episodes: a single fall-heavy episode should not
    move a gate. Episodes with no measurable window contribute to ``n_unscored``, not a zero.
    """
    scores = [e["tripod_score"] for e in episodes if e["tripod_score"] is not None]
    tips = [e["tippy_tap_fraction"] for e in episodes if e.get("tippy_tap_fraction") is not None]
    slips = [e["slip_ratio_mean"] for e in episodes if e.get("slip_ratio_mean") is not None]
    reasons: dict[str, int] = {}
    for e in episodes:
        reasons[e["termination_reason"]] = reasons.get(e["termination_reason"], 0) + 1

    def _stats(values: list[float]) -> dict:
        if not values:
            return {"median": None, "mean": None, "p25": None, "p75": None, "n": 0}
        arr = np.asarray(values, dtype=np.float64)
        return {
            "median": float(np.median(arr)),
            "mean": float(arr.mean()),
            "p25": float(np.percentile(arr, 25)),
            "p75": float(np.percentile(arr, 75)),
            "n": int(arr.size),
        }

    # Per-hold breakdown: tripod quality is usually speed-dependent, and one number hides that.
    per_hold: dict[str, list[float]] = {}
    for e in episodes:
        for label, hold in e["holds"].items():
            score = hold["tripod"].get("tripod_score")
            if score is not None and not hold["tripod"].get("low_confidence"):
                per_hold.setdefault(label, []).append(score)

    n_eps = len(episodes)
    return {
        "n_episodes": n_eps,
        "n_unscored_episodes": n_eps - len(scores),
        "tripod_score": _stats(scores),
        "tripod_score_by_hold": {k: _stats(v) for k, v in per_hold.items()},
        "tippy_tap_fraction": _stats(tips),
        "slip_ratio": _stats(slips),
        "termination_reasons": reasons,
        "schedule_completion_rate": (
            float(sum(1 for e in episodes if e["completed_schedule"]) / n_eps) if n_eps else None
        ),
    }


def summary_text(run_meta: dict, episodes: list[dict]) -> str:
    agg = aggregate(episodes)
    lines = [
        "=== crab-hex gait eval ===",
        f"scenario   : {run_meta['scenario_id']}  ({run_meta['task']})",
        f"checkpoint : {run_meta.get('checkpoint') or '(zero actions)'}",
        f"episodes   : {agg['n_episodes']}  unscored: {agg['n_unscored_episodes']}",
        f"terrain    : {run_meta.get('terrain_source')}",
        f"cmd override max deviation: {run_meta.get('command_override_max_deviation'):.3e}",
        "",
        f"tripod_score      median={agg['tripod_score']['median']}  "
        f"p25={agg['tripod_score']['p25']}  p75={agg['tripod_score']['p75']}",
        f"tippy_tap_fraction median={agg['tippy_tap_fraction']['median']}",
        f"slip_ratio         median={agg['slip_ratio']['median']}",
        f"schedule_completion_rate={agg['schedule_completion_rate']}",
        f"terminations={agg['termination_reasons']}",
    ]
    if agg["tripod_score_by_hold"]:
        lines.append("")
        lines.append("by hold:")
        for label, st in agg["tripod_score_by_hold"].items():
            lines.append(f"  {label:>8}: tripod median={st['median']} (n={st['n']})")
    for key in ("command_override_warning", "obs_dim_warning"):
        if run_meta.get(key):
            lines.append(f"\n[WARN] {run_meta[key]}")
    return "\n".join(lines)


def write_run(
    run_dir: Path,
    *,
    run_meta: dict,
    episode_metrics: list[dict],
    raw: dict[str, np.ndarray] | None,
    scenario: Scenario,
    compiled: CompiledSchedule | None = None,
    history_root: Path | None = None,
) -> None:
    run_dir = Path(run_dir)
    (run_dir / "metrics").mkdir(parents=True, exist_ok=True)
    agg = aggregate(episode_metrics)

    (run_dir / "run_meta.json").write_text(json.dumps(M.json_safe(run_meta), indent=2, sort_keys=True))
    for ep in episode_metrics:
        path = run_dir / "metrics" / f"episode_{ep['env_index']:02d}.json"
        path.write_text(json.dumps(M.json_safe(ep), indent=2, sort_keys=True))
    (run_dir / "scenario_metrics.json").write_text(
        json.dumps(
            M.json_safe(
                {
                    "scenario_id": scenario.id,
                    "aggregate": agg,
                    "run_meta": run_meta,
                    "episodes": [
                        {
                            "env_index": e["env_index"],
                            "tripod_score": e["tripod_score"],
                            "tippy_tap_fraction": e["tippy_tap_fraction"],
                            "slip_ratio_mean": e["slip_ratio_mean"],
                            "termination_reason": e["termination_reason"],
                            "n_steps": e["n_steps"],
                        }
                        for e in episode_metrics
                    ],
                }
            ),
            indent=2,
            sort_keys=True,
        )
    )
    (run_dir / "summary.md").write_text(
        "```\n" + summary_text(run_meta, episode_metrics) + "\n```\n"
    )

    if raw is not None:
        # Raw force norms (not just booleans) are saved so the contact threshold can be re-swept
        # offline without another GPU run -- the codebase is inconsistent about it (sensor cfg 1.0,
        # reward_foot_clearance 0.1).
        raw_dir = run_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        n_env = int(run_meta["num_envs"])
        for env_idx in range(n_env):
            n = int(run_meta["n_steps_per_env"][env_idx])
            payload = {k: np.asarray(v)[:n, env_idx] for k, v in raw.items()}
            if compiled is not None:
                payload["segment_id"] = compiled.segment_id[:n, env_idx]
                payload["steady_mask"] = compiled.steady_mask[:n, env_idx]
            payload["dt"] = np.asarray(run_meta["dt"], dtype=np.float64)
            np.savez_compressed(raw_dir / f"episode_{env_idx:02d}.npz", **payload)

    if history_root is not None:
        history_root = Path(history_root)
        history_root.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "scenario": scenario.id,
            "checkpoint": run_meta.get("checkpoint"),
            "checkpoint_sha256": run_meta.get("checkpoint_sha256"),
            "run_dir": str(run_dir),
            "aggregate": agg,
        }
        with (history_root / f"gait_eval_{scenario.id}.jsonl").open("a") as fh:
            fh.write(json.dumps(M.json_safe(record)) + "\n")
