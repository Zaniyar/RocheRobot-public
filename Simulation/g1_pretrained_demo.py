"""Interactive inference of NVIDIA's published Isaac Lab G1 flat PPO policy.

Uses Isaac Lab v2.3.2 task/robot and RSL-RL; no training or real-robot transport.
Reference: IsaacLab/scripts/reinforcement_learning/rsl_rl/play.py (BSD-3-Clause).
Our additions: velocity buttons, follow camera and a bounded measurement run.
"""
import argparse
# Load the venv's HDF5 DLL before GUI extensions add their DLL directories.
# The full GUI experience otherwise resolves an incompatible HDF5 DLL on Windows.
import h5py
from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--steps", type=int, default=0, help="0 keeps the window open")
parser.add_argument("--report", required=True)
parser.add_argument("--checkpoint", required=True)
parser.add_argument("--run-id", required=True)
parser.add_argument("--video", default="", help="Optional MP4 for a bounded test")
AppLauncher.add_app_launcher_args(parser)
args = parser.parse_args()
if args.video:
    args.enable_cameras = True
launcher = AppLauncher(args)
app = launcher.app

import hashlib
import json
import time
from pathlib import Path
import gymnasium as gym
import torch
from rsl_rl.runners import OnPolicyRunner
from isaaclab_rl.rsl_rl import RslRlVecEnvWrapper
import isaaclab_tasks  # registers official tasks
from isaaclab_tasks.utils import parse_env_cfg, load_cfg_from_registry

TASK = "Isaac-Velocity-Flat-G1-Play-v0"
EXPECTED_SHA = "fdf0f242bb8f3bcfc1aa9b7ff2761af4c014cf1cdc7e49242c9b92f3581720e7"


def main():
    checkpoint = Path(args.checkpoint)
    digest = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    if digest != EXPECTED_SHA:
        raise RuntimeError("Checkpoint differs from the verified official download")
    cfg = parse_env_cfg(TASK, device=args.device, num_envs=1)
    cfg.seed = 42
    cfg.episode_length_s = 1000000
    # Keep policy observations/actions/actuators unchanged. Replace only the
    # random high-level velocity command and random starting pose for the demo.
    cmd_cfg = cfg.commands.base_velocity
    cmd_cfg.heading_command = False
    cmd_cfg.rel_standing_envs = 0.0
    cmd_cfg.resampling_time_range = (1000000.0, 1000000.0)
    cmd_cfg.ranges.lin_vel_x = (0.0, 0.0)
    cmd_cfg.ranges.lin_vel_y = (0.0, 0.0)
    cmd_cfg.ranges.ang_vel_z = (0.0, 0.0)
    cfg.events.reset_base.params["pose_range"] = {"x": (0, 0), "y": (0, 0), "yaw": (0, 0)}
    cfg.viewer.eye = (2.8, 2.8, 2.0)
    cfg.viewer.lookat = (0.0, 0.0, 0.7)
    cfg.viewer.resolution = (960, 720)
    agent_cfg = load_cfg_from_registry(TASK, "rsl_rl_cfg_entry_point")
    agent_cfg.device = args.device
    agent_cfg.obs_groups = {"policy": ["policy"], "critic": ["policy"]}
    env = RslRlVecEnvWrapper(gym.make(TASK, cfg=cfg, render_mode="rgb_array" if args.video else None))
    runner = OnPolicyRunner(env, agent_cfg.to_dict(), log_dir=None, device=args.device)
    runner.load(str(checkpoint), load_optimizer=False)
    policy = runner.get_inference_policy(device=args.device)
    robot = env.unwrapped.scene["robot"]
    command = env.unwrapped.command_manager.get_command("base_velocity")
    state = {"demo": True, "velocity": [0.0, 0.0, 0.0], "reset": False, "tick": 0}
    label = None

    def select(velocity=None):
        state["demo"] = velocity is None
        state["velocity"] = velocity or [0.0, 0.0, 0.0]
        state["tick"] = 0

    if not args.headless:
        import omni.ui as ui
        import omni.appwindow
        import carb.input
        window = ui.Window("G1 | Fertige RL-Policy", width=380, height=280)
        with window.frame:
            with ui.VStack(spacing=8):
                ui.Label("Vortrainiertes PPO-Modell | KEIN Training", height=24)
                ui.Label("Die Demo startet automatisch. Befehle bleiben aktiv.", height=22)
                with ui.HStack(height=36):
                    ui.Button("Vorwaerts [W]", clicked_fn=lambda: select([0.5, 0, 0]))
                    ui.Button("STOPP [S / Leertaste]", clicked_fn=lambda: select([0, 0, 0]))
                with ui.HStack(height=36):
                    ui.Button("Links [A]", clicked_fn=lambda: select([0.35, 0, 0.5]))
                    ui.Button("Rechts [D]", clicked_fn=lambda: select([0.35, 0, -0.5]))
                with ui.HStack(height=36):
                    ui.Button("Demo [M]", clicked_fn=lambda: select())
                    ui.Button("Reset [R]", clicked_fn=lambda: state.update(reset=True))
                label = ui.Label("Policy wird ausgefuehrt", height=36, word_wrap=True)
                ui.Label("G1-Laufen; noch kein Greifen des Roche-Kits.", height=22)
        controls = {"W": [0.5, 0, 0], "S": [0, 0, 0], "SPACE": [0, 0, 0],
                    "A": [0.35, 0, 0.5], "D": [0.35, 0, -0.5]}

        def key_event(event):
            if event.type == carb.input.KeyboardEventType.KEY_PRESS:
                key = event.input.name
                if key in controls:
                    select(controls[key])
                elif key == "M":
                    select()
                elif key == "R":
                    state["reset"] = True
            return True

        input_api = carb.input.acquire_input_interface()
        keyboard = omni.appwindow.get_default_app_window().get_keyboard()
        keyboard_subscription = input_api.subscribe_to_keyboard_events(keyboard, key_event)

    writer = None
    if args.video:
        import imageio.v2 as imageio
        Path(args.video).parent.mkdir(parents=True, exist_ok=True)
        writer = imageio.get_writer(args.video, fps=25, macro_block_size=8)
    initial_joints = robot.data.joint_pos.clone()
    samples = []
    resets = 0
    manual_resets = 0
    min_z = float("inf")
    max_joint_change = 0.0
    tick = 0
    print("G1_POLICY_READY " + json.dumps({"run_id": args.run_id, "task": TASK,
          "joints": robot.num_joints, "checkpoint_sha256": digest, "training": False}), flush=True)
    try:
        while app.is_running() and (args.steps == 0 or tick < args.steps):
            start = time.perf_counter()
            if state["reset"]:
                env.reset()
                state["reset"] = False
                state["tick"] = 0
                manual_resets += 1
            # 2 s settle, 4 s forward, 4 s left turn, 2 s stop; repeats.
            phase = (state["tick"] * env.unwrapped.step_dt) % 12
            velocity = ([0, 0, 0] if phase < 2 or phase >= 10 else
                        [0.5, 0, 0] if phase < 6 else [0.35, 0, 0.5]) if state["demo"] else state["velocity"]
            with torch.inference_mode():
                command[:] = torch.tensor(velocity, device=args.device)
                obs = env.get_observations()
                actions = policy(obs)
                if not torch.isfinite(actions).all():
                    raise RuntimeError("Non-finite policy actions")
                _, _, dones, _ = env.step(actions)
                runner.alg.policy.reset(dones)
                resets += int(dones.sum().item())
                position = robot.data.root_pos_w[0].tolist()
                min_z = min(min_z, position[2])
                max_joint_change = max(max_joint_change, (robot.data.joint_pos - initial_joints).abs().max().item())
                if tick % 10 == 0:
                    samples.append({"step": tick, "time_s": round(tick * env.unwrapped.step_dt, 3),
                                    "command": velocity, "position_m": position,
                                    "velocity_body_m_s": robot.data.root_lin_vel_b[0].tolist(),
                                    "yaw_rate_rad_s": robot.data.root_ang_vel_b[0, 2].item()})
            if tick % 2 == 0:
                env.unwrapped.sim.set_camera_view(
                    [position[0]+2.8, position[1]+2.8, 2.0], [position[0], position[1], 0.7])
                if writer:
                    writer.append_data(env.unwrapped.render())
            if label is not None and tick % 10 == 0:
                label.text = f"{'DEMO' if state['demo'] else 'MANUELL'} | vorwaerts {velocity[0]:.2f} m/s | drehen {velocity[2]:.2f} rad/s"
            tick += 1
            state["tick"] += 1
            if not args.headless:
                time.sleep(max(0, env.unwrapped.step_dt - (time.perf_counter() - start)))
        report = {"run_id": args.run_id, "task": TASK, "checkpoint_sha256": digest,
                  "steps": tick, "simulated_seconds": tick * env.unwrapped.step_dt,
                  "joint_count": robot.num_joints, "joint_names": robot.joint_names,
                  "min_base_height_m": min_z, "max_joint_change_rad": max_joint_change,
                  "automatic_resets": resets, "manual_resets": manual_resets,
                  "training": False, "roche_manipulation": False, "samples": samples}
        Path(args.report).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("G1_POLICY_FINISHED " + json.dumps({k: v for k, v in report.items() if k not in ("samples", "joint_names")}), flush=True)
    finally:
        if writer:
            writer.close()
        env.close()


if __name__ == "__main__":
    main()
    app.close()
