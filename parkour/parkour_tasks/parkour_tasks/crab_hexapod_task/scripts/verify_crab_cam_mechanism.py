# SPDX-License-Identifier: BSD-3-Clause
"""Verify the crab-hex cam-mechanism kinematic coupling: for each converted leg's
``*_Body_CamShaft_RevoluteJoint`` -> ``*_Body_Hip_RevoluteJoint`` pair, drive the shaft to a
few different target angles via normal policy-style actions, let it settle under real PD
dynamics, then assert the hip joint's settled position tracks
``crab_hex_cam_mapping.cam_shaft_to_hip(shaft's settled position)`` within a reasonable
tolerance.

NOTE(cam-mechanism-migration): an earlier version of this script forced the shaft's state
directly via ``Articulation.write_joint_state_to_sim`` and checked the hip joint's response
immediately (no physics stepping), expecting a near-exact match. That matched the coupling
code's *old* design (direct state teleportation each substep), which was abandoned after it
was found to freeze the whole articulation's dynamics -- see parkour_actions.py's docstring.
The coupling now works via ``set_joint_position_target`` (real PD tracking, like every other
joint), so this script settles via ``env.step()`` and checks with a real-PD-appropriate
tolerance instead of near-zero.

Also checks the post-reset default pose is self-consistent: hip's default_joint_pos should
be close to cam_shaft_to_hip(shaft's default_joint_pos), since crab_hex_scene_cfg.py's
init_state.joint_pos values were chosen to satisfy this (allowing for settling under gravity).
"""

from __future__ import annotations

import argparse
import math
import sys

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser(
    description="Sweep each converted leg's cam-shaft joint and verify the passive hip joint tracks the mapping."
)
parser.add_argument(
    "--task",
    type=str,
    default="Isaac-Crab-Hex-Flat-Walk-Play-v0",
    help="Parkour crab env (play or train cfg both work).",
)
parser.add_argument(
    "--disable_fabric",
    action="store_true",
    default=False,
    help="Disable fabric and use USD I/O operations.",
)
parser.add_argument("--num_envs", type=int, default=1)
parser.add_argument(
    "--raw_actions",
    type=float,
    nargs="+",
    default=[-1.0, -0.5, 0.0, 0.5, 1.0],
    help="Raw CamShaft actions to test (clipped to [-1,1]; target = raw*scale + default_joint_pos).",
)
parser.add_argument("--settle_steps", type=int, default=100, help="Steps to hold each action before sampling.")
parser.add_argument(
    "--pos_tol_rad",
    type=float,
    default=0.08,
    help="Max allowed |hip_pos - expected(shaft_actual)| after settling (real PD tracking, not exact).",
)
parser.add_argument(
    "--default_pos_tol_rad",
    type=float,
    default=0.05,
    help="Max allowed default-pose inconsistency (settled under gravity, not an exact write).",
)
AppLauncher.add_app_launcher_args(parser)
args_cli = parser.parse_args()

app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

from _paths import parkour_root, parkour_scripts_dir

_parkour_root = parkour_root()
_parkour_scripts = parkour_scripts_dir()
for _p in (str(_parkour_scripts), str(_parkour_root / "parkour_tasks")):
    while _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, str(_parkour_root))
sys.path.insert(0, str(_parkour_root / "parkour_tasks"))

import gymnasium as gym
import torch

import parkour_tasks  # noqa: F401
from isaaclab_tasks.utils import parse_env_cfg

from parkour_tasks.crab_hexapod_task.mdp.crab_hex_cam_mapping import cam_shaft_to_hip


def main() -> None:
    env_cfg = parse_env_cfg(
        args_cli.task,
        device=args_cli.device,
        num_envs=args_cli.num_envs,
        use_fabric=not args_cli.disable_fabric,
    )
    if hasattr(env_cfg, "parkours") and env_cfg.parkours is not None:
        env_cfg.parkours.base_parkour.debug_vis = False
    if hasattr(env_cfg, "commands") and env_cfg.commands is not None:
        env_cfg.commands.base_velocity.debug_vis = False

    env = gym.make(args_cli.task, cfg=env_cfg)
    with torch.inference_mode():
        env.reset()

    robot = env.unwrapped.scene["robot"]
    action_term = env.unwrapped.action_manager.get_term("joint_pos")
    device = env.unwrapped.device

    shaft_ids, shaft_names = robot.find_joints([".*_Body_CamShaft_RevoluteJoint"], preserve_order=True)
    hip_names = [name.replace("_Body_CamShaft_RevoluteJoint", "_Body_Hip_RevoluteJoint") for name in shaft_names]
    hip_ids, _ = robot.find_joints(hip_names, preserve_order=True)

    # Resolve each shaft joint's position within the action vector (order matches action_term's
    # own joint resolution, found by intersecting its _joint_ids with our shaft_ids).
    action_joint_ids = list(action_term._joint_ids)
    shaft_action_idx = [action_joint_ids.index(jid) for jid in shaft_ids]

    print("\n=== Crab cam-mechanism coupling check ===", flush=True)
    print(f"task: {args_cli.task}", flush=True)
    print(f"num_envs: {env.unwrapped.scene.num_envs}", flush=True)
    print(f"converted legs (cam-shaft joints found): {shaft_names}", flush=True)
    print(f"corresponding hip joints: {hip_names}", flush=True)
    if not shaft_names:
        print("FAIL: no *_Body_CamShaft_RevoluteJoint found -- has the prototype been built?", flush=True)
        env.close()
        sys.exit(1)

    all_ok = True

    def _settle(n: int) -> None:
        zero_actions = torch.zeros(env.action_space.shape, device=device)
        with torch.inference_mode():
            for _ in range(n):
                env.step(zero_actions)

    def _check(label: str, tol: float) -> tuple[float, list]:
        shaft_actual = robot.data.joint_pos[:, shaft_ids]
        hip_actual = robot.data.joint_pos[:, hip_ids]
        zero_vel = torch.zeros_like(shaft_actual)
        expected_hip, _ = cam_shaft_to_hip(shaft_actual, zero_vel)
        err = (hip_actual - expected_hip).abs()
        max_err = err.max().item()
        ok = max_err <= tol
        rows = []
        for i, name in enumerate(shaft_names):
            rows.append(
                f"[{name}] shaft={shaft_actual[0, i].item():+.4f}  hip={hip_actual[0, i].item():+.4f}  "
                f"expected={expected_hip[0, i].item():+.4f}  err={err[0, i].item():.4f}"
            )
        print(f"\n--- {label} (tol {tol}) ---", flush=True)
        for row in rows:
            print(row, flush=True)
        print(f"max err = {max_err:.4f}  ({'ok' if ok else 'FAIL'})", flush=True)
        return max_err, [ok]

    # --- 1. Default pose settled under gravity ---
    _settle(args_cli.settle_steps)
    default_err, default_oks = _check("post-settle default pose", args_cli.default_pos_tol_rad)
    all_ok = all_ok and all(default_oks)

    # --- 2. Drive CamShaft through several target actions, settle, check tracking ---
    max_pos_err = default_err
    n_checked = 0
    n_failed = 0
    for raw in args_cli.raw_actions:
        actions = torch.zeros(env.action_space.shape, device=device)
        for idx in shaft_action_idx:
            actions[:, idx] = raw
        with torch.inference_mode():
            for _ in range(args_cli.settle_steps):
                env.step(actions)
        err, oks = _check(f"raw_action={raw:+.2f}", args_cli.pos_tol_rad)
        n_checked += 1
        max_pos_err = max(max_pos_err, err)
        if not all(oks):
            n_failed += 1

    sweep_ok = n_failed == 0
    all_ok = all_ok and sweep_ok
    print(f"\nchecked {n_checked} target actions: {args_cli.raw_actions}", flush=True)
    print(f"max |hip_pos err| across all checks = {max_pos_err:.4f} rad", flush=True)
    print(f"failed: {n_failed}/{n_checked}", flush=True)

    env.close()

    print("\n=== Summary ===", flush=True)
    if all_ok:
        print("PASS: default pose consistent and hip joint tracks cam_shaft_to_hip() across the full sweep.", flush=True)
    else:
        print("FAIL: see details above.", flush=True)
    print(flush=True)
    if not all_ok:
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    finally:
        simulation_app.close()
