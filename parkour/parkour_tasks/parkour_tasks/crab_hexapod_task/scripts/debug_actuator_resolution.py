# SPDX-License-Identifier: BSD-3-Clause
"""One-off diagnostic: print resolved actuator groups and drive FL knee directly.

Bypasses the action pipeline (set_joint_position_target straight on the articulation)
to separate 'actuator misconfigured' from 'action term broken'.
"""

from __future__ import annotations

import argparse
import sys

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser()
parser.add_argument("--task", type=str, default="Isaac-Crab-Hex-Flat-Walk-Play-v0")
parser.add_argument("--num_envs", type=int, default=1)
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


def main() -> None:
    env_cfg = parse_env_cfg(args_cli.task, device=args_cli.device, num_envs=args_cli.num_envs)
    env_cfg.sim.gravity = (0.0, 0.0, 0.0)
    env_cfg.scene.robot.spawn.rigid_props.disable_gravity = True
    env = gym.make(args_cli.task, cfg=env_cfg)
    robot = env.unwrapped.scene["robot"]

    print("\n=== Resolved actuator groups ===", flush=True)
    for group_name, act in robot.actuators.items():
        names = act.joint_names
        stiff = act.stiffness[0].tolist()
        damp = act.damping[0].tolist()
        eff = act.effort_limit[0].tolist()
        vel = act.velocity_limit[0].tolist() if hasattr(act, "velocity_limit") else None
        print(f"[{group_name}] type={type(act).__name__}", flush=True)
        for i, n in enumerate(names):
            v = f" vel_lim={vel[i]:.1f}" if vel is not None else ""
            print(
                f"    {n}: k={stiff[i]:.2f} d={damp[i]:.3f} effort_lim={eff[i]:.1f}{v}",
                flush=True,
            )

    joint_names = list(robot.data.joint_names)
    knee_id = joint_names.index("FL_Femur_Tibia_RevoluteJoint")
    term = env.unwrapped.action_manager.get_term("joint_pos")
    knee_col = list(term._joint_names).index("FL_Femur_Tibia_RevoluteJoint")
    print(f"\n=== Drive FL knee via action col {knee_col} (dof {knee_id}) ===", flush=True)
    with torch.inference_mode():
        env.reset()
        zero = torch.zeros(env.action_space.shape, device=env.unwrapped.device)
        for _ in range(48):
            env.step(zero)
        q0 = robot.data.joint_pos[0, knee_id].item()
        print(f"start q={q0:+.4f}", flush=True)
        scale = term._scale if isinstance(term._scale, float) else term._scale[0, knee_col].item()
        offset = term._offset if isinstance(term._offset, float) else term._offset[0, knee_col].item()
        print(
            f"term internals: use_delay={term._use_delay} delay={term.delay} "
            f"hist_len={term._action_history_buf.shape[1]} scale={scale} offset={offset:+.4f}",
            flush=True,
        )
        act = zero.clone()
        act[..., knee_col] = 1.0
        for step in range(120):
            env.step(act)
            if step % 20 == 0 or step == 119:
                q = robot.data.joint_pos[0, knee_id].item()
                tgt = robot.data.joint_pos_target[0, knee_id].item()
                tau = robot.data.applied_torque[0, knee_id].item()
                raw = term.raw_actions[0, knee_col].item()
                proc = term._processed_actions[0, knee_col].item()
                hist = term._action_history_buf[0, :, knee_col].tolist()
                print(
                    f"  step {step:3d}: q={q:+.4f} target={tgt:+.4f} tau={tau:+.2f} "
                    f"raw={raw:+.2f} proc={proc:+.4f} delay={term.delay} "
                    f"hist={[round(h, 2) for h in hist]}",
                    flush=True,
                )
    env.close()


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        import traceback

        traceback.print_exc()
        raise
    finally:
        simulation_app.close()
