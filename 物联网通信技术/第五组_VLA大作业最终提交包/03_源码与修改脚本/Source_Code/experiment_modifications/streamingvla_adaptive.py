import collections
import csv
import dataclasses
import logging
import math
import pathlib
import time 

import imageio
from libero.libero import benchmark
from libero.libero import get_libero_path
from libero.libero.envs import OffScreenRenderEnv
import numpy as np
from openpi_client import image_tools
from openpi_client import streaming_websocket_client_policy as _websocket_client_policy
import tqdm
import tyro
from typing import Optional, List, Tuple

try:
    from adaptive_horizon_policy import (
        ChunkConsistencyAdaptiveHorizon,
        summarize_errors,
        summarize_horizon_sequence,
    )
except ImportError:  # Keep the original fixed-horizon runner usable if copied alone.
    ChunkConsistencyAdaptiveHorizon = None
    summarize_errors = None
    summarize_horizon_sequence = None

LIBERO_DUMMY_ACTION = [0.0] * 6 + [-1.0]
LIBERO_ENV_RESOLUTION = 256 # resolution used to render training data

@dataclasses.dataclass
class Args:
    
    host: str = "0.0.0.0"
    port: int = 8000
    resize_size: int = 224
    replan_steps: int = 10
    timing_output_path: str = "your_timing_path" 
    task_suite_name: str = (
        "libero_object"  # Task suite. Options: libero_spatial, libero_object, libero_goal, libero_10, libero_90
    )
    num_steps_wait: int = 10  
    num_trials_per_task: int = 50  
    video_out_path: str = "your_video_path"  

    seed: int = 7  # Random Seed (for reproducibility)

    use_judger: bool = True # To decide whether to use the judger's feedback for replanning
    action_left: int = 2 # Number of actions left threshold to trigger the judger check
    threshold: float = 4.43 # Threshold for the judger's confidence to decide whether to jump to a new observation

    # --- Profiling / Horizon experiment args ---
    # Path to write per-episode profiling CSV. Empty string disables profiling.
    profiling_csv_path: str = ""
    # Label written into the CSV method column (e.g. "baseline", "h4", "h8").
    method_name: str = "baseline"
    # When True, forces use_judger=False so replan_steps == actual execution horizon.
    fixed_horizon_mode: bool = False
    # Adaptive exploration: choose horizon from recent chunk/action consistency.
    adaptive_horizon_mode: bool = False
    adaptive_min_horizon: int = 6
    adaptive_mid_horizon: int = 8
    adaptive_max_horizon: int = 10
    adaptive_tau_low: float = 0.03
    adaptive_tau_high: float = 0.07


_PROFILING_FIELDS = [
    "episode_id",
    "task_id",
    "task_name",
    "horizon",
    "method",
    "seed",
    "inference_count",
    "task_completion_steps",
    "episode_wall_time_ms",
    "task_success",
    "avg_model_inference_time_ms",
    "avg_total_latency_ms",
    "selected_horizon_mean",
    "selected_horizon_min",
    "selected_horizon_max",
    "selected_horizon_sequence",
    "consistency_error_mean",
    "consistency_error_max",
    "gripper_change_count",
    "adaptive_signal_source",
    "result_source",
]


def eval_libero(args: Args) -> None:
    # Apply fixed-horizon mode: disable AEO judger so replan_steps == execution horizon
    if args.fixed_horizon_mode:
        args.use_judger = False
    if args.adaptive_horizon_mode:
        args.use_judger = False
        args.fixed_horizon_mode = True
        if ChunkConsistencyAdaptiveHorizon is None:
            raise ImportError("adaptive_horizon_policy.py is required for adaptive_horizon_mode")

    adaptive_policy = None
    if args.adaptive_horizon_mode:
        adaptive_policy = ChunkConsistencyAdaptiveHorizon(
            min_horizon=args.adaptive_min_horizon,
            mid_horizon=args.adaptive_mid_horizon,
            max_horizon=args.adaptive_max_horizon,
            tau_low=args.adaptive_tau_low,
            tau_high=args.adaptive_tau_high,
        )

    # Set random seed
    np.random.seed(args.seed)

    # Initialize LIBERO task suite
    benchmark_dict = benchmark.get_benchmark_dict()
    task_suite = benchmark_dict[args.task_suite_name]()
    num_tasks_in_suite = task_suite.n_tasks
    logging.info(f"Task suite: {args.task_suite_name}")

    pathlib.Path(args.video_out_path).mkdir(parents=True, exist_ok=True)

    if args.task_suite_name == "libero_spatial":
        max_steps = 220 
    elif args.task_suite_name == "libero_object":
        max_steps = 280 
    elif args.task_suite_name == "libero_goal":
        max_steps = 300 
    elif args.task_suite_name == "libero_10":
        max_steps = 520 
    elif args.task_suite_name == "libero_90":
        max_steps = 400 
    else:
        raise ValueError(f"Unknown task suite: {args.task_suite_name}")

    client = _websocket_client_policy.WebsocketClientPolicy(args.host, args.port)
    suite_total_episodes, suite_total_successes = 0, 0
    suite_total_time_success, suite_total_actions_success = 0.0, 0

    # Open profiling CSV if requested
    csv_file = None
    csv_writer = None
    if args.profiling_csv_path:
        pathlib.Path(args.profiling_csv_path).parent.mkdir(parents=True, exist_ok=True)
        csv_file = open(args.profiling_csv_path, "w", newline="", encoding="utf-8")
        csv_writer = csv.DictWriter(csv_file, fieldnames=_PROFILING_FIELDS)
        csv_writer.writeheader()
        logging.info(f"Profiling CSV: {args.profiling_csv_path}")

    pathlib.Path(args.timing_output_path).parent.mkdir(parents=True, exist_ok=True)

    global_episode_id = 0

    try:
        with open(args.timing_output_path, 'w', encoding='utf-8') as timing_file:
            timing_file.write(f"--- Timing Results for Task Suite: {args.task_suite_name} (Success-Only Metrics) ---\n")
            timing_file.write(f"Method: {args.method_name} | Horizon: {args.replan_steps} | fixed_horizon_mode: {args.fixed_horizon_mode} | adaptive_horizon_mode: {args.adaptive_horizon_mode}\n")
            timing_file.write("Task | Episode | Success | Total Time (s) | Actions | Speed (s/action)\n")
            timing_file.write("-" * 80 + "\n")
        
            for task_id in tqdm.tqdm(range(num_tasks_in_suite), desc="Overall Task Suite"):
                task = task_suite.get_task(task_id)
                initial_states = task_suite.get_task_init_states(task_id)
                env, task_description = _get_libero_env(task, LIBERO_ENV_RESOLUTION, args.seed)
                
                logging.info(f"\n--- Starting Task {task_id+1}/{num_tasks_in_suite}: {task_description} ---")

                task_episode_results: List[Tuple[bool, float, int]] = [] 
                task_successful_episodes_data: List[Tuple[float, int]] = []
                task_sim_time_list: List[float] = [] 

                for episode_idx in tqdm.tqdm(range(args.num_trials_per_task)):
                    logging.info(f"\nTask: {task_description} | Episode: {episode_idx + 1}")
                   
                    env.reset()
                    obs = env.set_init_state(initial_states[episode_idx])

                    # Per-episode state
                    t = 0
                    replay_images = []
                    steps_since_replan = 0 
                    action_states = np.zeros(7, dtype=np.float32)
                    episode_start_time = 0.0 
                    episode_actions = 0
                    jump_times = 0
                    obs_times = 0
                    episode_success = False
                    done = False  # guard: env.step may never be reached if exception fires early
                    norm_new_obs = True
                    new_task = True
                    current_horizon = args.replan_steps
                    current_replan_actions: List[List[float]] = []
                    selected_horizons: List[int] = []
                    consistency_errors: List[float] = []
                    gripper_change_count = 0
                    adaptive_signal_source = "disabled"

                    # Profiling accumulators
                    infer_times_ms: List[float] = []   # model_inference_time per replan
                    latency_times_ms: List[float] = [] # total_latency per action step
                    
                    while t < max_steps + args.num_steps_wait:
                        try:
                            # Stabilization steps
                            if t < args.num_steps_wait:
                                obs, reward, done, info = env.step(LIBERO_DUMMY_ACTION)
                                t += 1
                                continue

                            # Start episode wall-clock after stabilization
                            if episode_start_time == 0.0:
                                episode_start_time = time.monotonic()
                            
                            # Image preprocessing
                            img = np.ascontiguousarray(obs["agentview_image"][::-1, ::-1])
                            wrist_img = np.ascontiguousarray(obs["robot0_eye_in_hand_image"][::-1, ::-1])
                            img = image_tools.convert_to_uint8(image_tools.resize_with_pad(img, args.resize_size, args.resize_size))
                            wrist_img = image_tools.convert_to_uint8(image_tools.resize_with_pad(wrist_img, args.resize_size, args.resize_size))
                            replay_images.append(img)

                            # Latency start: observation ready, about to infer / wait for action
                            t_latency_start = time.monotonic()

                            # --- AEO judger early-observation path ---
                            if (args.use_judger and steps_since_replan == (args.replan_steps - args.action_left) % args.replan_steps):
                                action_left_sum = client.get_left_queue_actions()
                                print(f"action_left_sum: {action_left_sum}")
                                if not np.any(action_left_sum):
                                    action_left_sum = None
                                    norm_new_obs = True
                                if action_left_sum is not None:
                                    element = {
                                        "observation/image": img,
                                        "observation/wrist_image": wrist_img,
                                        "observation/state": np.concatenate(
                                            (
                                                obs["robot0_eef_pos"],
                                                _quat2axisangle(obs["robot0_eef_quat"]),
                                                obs["robot0_gripper_qpos"],
                                            )
                                        ),
                                        "prompt": str(task_description),
                                        "observation/action_left_sum": action_left_sum,
                                        "observation/action_states": action_states,
                                        "observation/threshold": args.threshold,
                                    }
                                    jump_times += 1
                                    obs_times += 1
                                    norm_new_obs = False
                                    t_infer_start = time.monotonic()
                                    clear_queue = new_task or args.fixed_horizon_mode
                                    client.infer(element, clear_queue)
                                    infer_times_ms.append((time.monotonic() - t_infer_start) * 1000)

                            # --- Normal replan path ---
                            if steps_since_replan == 0 and norm_new_obs:
                                if adaptive_policy is not None:
                                    if current_replan_actions:
                                        decision = adaptive_policy.choose_from_executed_actions(current_replan_actions)
                                        current_horizon = decision.selected_horizon
                                        adaptive_signal_source = decision.signal_source
                                        consistency_errors.append(decision.consistency_error)
                                        if decision.gripper_changed:
                                            gripper_change_count += 1
                                    else:
                                        current_horizon = args.replan_steps
                                        adaptive_signal_source = "initial_horizon"
                                        consistency_errors.append(0.0)
                                    selected_horizons.append(current_horizon)
                                    current_replan_actions = []

                                element = {
                                    "observation/image": img,
                                    "observation/wrist_image": wrist_img,
                                    "observation/state": np.concatenate(
                                        (
                                            obs["robot0_eef_pos"],
                                            _quat2axisangle(obs["robot0_eef_quat"]),
                                            obs["robot0_gripper_qpos"],
                                        )
                                    ),
                                    "prompt": str(task_description),
                                    "observation/action_left_sum": None,
                                    "observation/action_states": action_states,
                                    "observation/threshold": 100000.0,
                                }
                                obs_times += 1
                                clear_queue = new_task or args.fixed_horizon_mode
                                t_infer_start = time.monotonic()
                                client.infer(element, clear_queue)
                                infer_times_ms.append((time.monotonic() - t_infer_start) * 1000)
                                new_task = False
                                
                            # Wait for next action from server
                            while True:                      
                                action_data = client.get_next_action(timeout=20)                       
                                if action_data is not None:
                                    break
                            
                            # Record end-to-end latency for this step
                            latency_times_ms.append((time.monotonic() - t_latency_start) * 1000)

                            if "norm_exceeded" in action_data:
                                norm_new_obs = True                         
                                continue

                            if "actions" in action_data:
                                episode_actions += 1
                                action = action_data["actions"]
                                action_states += action
                                if adaptive_policy is not None:
                                    current_replan_actions.append(action.tolist())

                                sim_time = time.monotonic()
                                obs, reward, done, info = env.step(action.tolist())
                                sim_end_time = time.monotonic() - sim_time
                                task_sim_time_list.append(sim_end_time)
                                steps_since_replan = (steps_since_replan + 1) % current_horizon
                                
                                t += 1
                             
                            if done:
                                episode_success = True
                                break

                        except Exception as e:
                            logging.error(f"Caught exception: {e}")
                            break

                    # --- Episode end ---
                    episode_end_time = time.monotonic()
                    suffix = "success" if done else "failure"
                    
                    imageio.mimwrite(
                        pathlib.Path(args.video_out_path) / f"{task_description}_{task_id}_{(episode_idx)%3}_{suffix}.mp4",
                        [np.asarray(x) for x in replay_images],
                        fps=20,
                    )

                    if episode_start_time > 0:
                        episode_total_time = episode_end_time - episode_start_time
                    else:
                        episode_total_time = 0.0
                        episode_actions = 0

                    task_episode_results.append((episode_success, episode_total_time, episode_actions))

                    if episode_success:
                        task_successful_episodes_data.append((episode_total_time, episode_actions))
                        action_speed = episode_total_time / episode_actions if episode_actions > 0 else 0.0
                        timing_file.write(f"{episode_idx + 1:7d} | SUCCESS | {episode_total_time:14.2f} | {episode_actions:7d} | {action_speed:14.4f}\n")
                    
                    success_status = "SUCCESS" if episode_success else "FAILURE"
                    logging.info(f"Episode {episode_idx + 1} Result: {success_status} | Time: {episode_total_time:.2f} s | Actions: {episode_actions}")

                    # Write profiling CSV row
                    if csv_writer is not None:
                        avg_infer_ms = sum(infer_times_ms) / len(infer_times_ms) if infer_times_ms else 0.0
                        avg_latency_ms = sum(latency_times_ms) / len(latency_times_ms) if latency_times_ms else 0.0
                        if adaptive_policy is not None:
                            horizon_summary = summarize_horizon_sequence(selected_horizons)
                            error_summary = summarize_errors(consistency_errors)
                            row_horizon = round(horizon_summary["selected_horizon_mean"], 3)
                            result_source = "real_adaptive_rollout"
                        else:
                            horizon_summary = {
                                "selected_horizon_mean": "",
                                "selected_horizon_min": "",
                                "selected_horizon_max": "",
                                "selected_horizon_sequence": "",
                            }
                            error_summary = {
                                "consistency_error_mean": "",
                                "consistency_error_max": "",
                            }
                            row_horizon = args.replan_steps
                            result_source = "real_fixed_horizon_rollout"
                        csv_writer.writerow({
                            "episode_id": global_episode_id,
                            "task_id": task_id,
                            "task_name": task_description,
                            "horizon": row_horizon,
                            "method": args.method_name,
                            "seed": args.seed,
                            "inference_count": obs_times,
                            "task_completion_steps": episode_actions,
                            "episode_wall_time_ms": round(episode_total_time * 1000, 2),
                            "task_success": int(episode_success),
                            "avg_model_inference_time_ms": round(avg_infer_ms, 3),
                            "avg_total_latency_ms": round(avg_latency_ms, 3),
                            "selected_horizon_mean": horizon_summary["selected_horizon_mean"],
                            "selected_horizon_min": horizon_summary["selected_horizon_min"],
                            "selected_horizon_max": horizon_summary["selected_horizon_max"],
                            "selected_horizon_sequence": horizon_summary["selected_horizon_sequence"],
                            "consistency_error_mean": error_summary["consistency_error_mean"],
                            "consistency_error_max": error_summary["consistency_error_max"],
                            "gripper_change_count": gripper_change_count,
                            "adaptive_signal_source": adaptive_signal_source,
                            "result_source": result_source,
                        })
                        if csv_file is not None:
                            csv_file.flush()

                    global_episode_id += 1

                num_trials = len(task_episode_results)
                num_successes = len(task_successful_episodes_data)

                if num_trials > 0:
                    task_avg_success_rate = num_successes / num_trials
                    if num_successes > 0:
                        task_success_only_time = sum(t for t, _ in task_successful_episodes_data)
                        task_success_only_actions = sum(a for _, a in task_successful_episodes_data)
                        
                        task_avg_time_success = task_success_only_time / num_successes 
                        task_avg_actions_success = task_success_only_actions / num_successes 
                        task_avg_speed = task_success_only_actions / task_success_only_time if task_success_only_time > 0 else 0.0 
                        
                        suite_total_time_success += task_success_only_time
                        suite_total_actions_success += task_success_only_actions
                    else:
                        task_avg_time_success, task_avg_actions_success, task_avg_speed = 0.0, 0.0, 0.0

                    task_avg_sim_time = sum(task_sim_time_list) / len(task_sim_time_list) if task_sim_time_list else 0.0
                    
                    timing_file.write("-" * 80 + "\n")
                    timing_file.write(f"Task Summary: {task_description}\n")
                    timing_file.write(f"  Avg Success Rate (All Trials): {task_avg_success_rate:.4f} ({num_successes}/{num_trials})\n")
                    timing_file.write(f"  Avg Episode Time (Success Only): {task_avg_time_success:.2f} seconds\n")
                    timing_file.write(f"  Avg Actions/Episode (Success Only): {task_avg_actions_success:.2f} actions\n")
                    timing_file.write(f"  Avg Action Speed (Success Only): {task_avg_speed:.2f} actions/second\n")
                    timing_file.write(f"  Avg Sim Step Time: {task_avg_sim_time * 1000:.4f} ms\n")
                    timing_file.write("=" * 80 + "\n\n")

                    suite_total_episodes += num_trials
                    suite_total_successes += num_successes

                    logging.info(f"Task Success Rate: {task_avg_success_rate:.4f}")

            current_suite_avg_success_rate = suite_total_successes / suite_total_episodes if suite_total_episodes > 0 else 0.0
            logging.info(f"Current Total Success Rate: {current_suite_avg_success_rate * 100:.1f}%")

            if suite_total_successes > 0:
                suite_avg_success_rate = suite_total_successes / suite_total_episodes
                suite_avg_time_success = suite_total_time_success / suite_total_successes
                suite_avg_actions_success = suite_total_actions_success / suite_total_successes
                suite_avg_speed_success = suite_total_actions_success / suite_total_time_success if suite_total_time_success > 0 else 0.0
            else:
                suite_avg_success_rate, suite_avg_time_success, suite_avg_actions_success, suite_avg_speed_success = 0.0, 0.0, 0.0, 0.0
                
            timing_file.write("\n\n")
            timing_file.write("################################################################################\n")
            timing_file.write("### OVERALL SUITE SUMMARY ###\n")
            timing_file.write("################################################################################\n")
            timing_file.write(f"Total Tasks Completed: {num_tasks_in_suite}\n")
            timing_file.write(f"Total Episodes Attempted: {suite_total_episodes}\n")
            timing_file.write(f"Total Successful Episodes: {suite_total_successes}\n")
            timing_file.write(f"Overall Success Rate (All Trials): {suite_avg_success_rate:.4f} ({suite_total_successes}/{suite_total_episodes})\n")
            timing_file.write(f"Overall Avg Episode Time (Success Only): {suite_avg_time_success:.2f} seconds\n")
            timing_file.write(f"Overall Avg Actions/Episode (Success Only): {suite_avg_actions_success:.2f} actions\n")
            timing_file.write(f"Overall Avg Action Speed (Success Only): {suite_avg_speed_success:.2f} actions/second\n")

            logging.info(f"Total success rate: {suite_avg_success_rate:.4f}")
            logging.info(f"Total episodes: {suite_total_episodes}")

    finally:
        if csv_file is not None:
            csv_file.close()


def _get_libero_env(task, resolution, seed):
    task_description = task.language
    task_bddl_file = pathlib.Path(get_libero_path("bddl_files")) / task.problem_folder / task.bddl_file
    env_args = {"bddl_file_name": task_bddl_file, "camera_heights": resolution, "camera_widths": resolution}
    env = OffScreenRenderEnv(**env_args)
    env.seed(seed)  
    return env, task_description


def _quat2axisangle(quat):
    """
    Copied from robosuite: https://github.com/ARISE-Initiative/robosuite/blob/eafb81f54ffc104f905ee48a16bb15f059176ad3/robosuite/utils/transform_utils.py#L490C1-L512C55
    """
    if quat[3] > 1.0:
        quat[3] = 1.0
    elif quat[3] < -1.0:
        quat[3] = -1.0

    den = np.sqrt(1.0 - quat[3] * quat[3])
    if math.isclose(den, 0.0):
        return np.zeros(3)

    return (quat[:3] * 2.0 * math.acos(quat[3])) / den


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    tyro.cli(eval_libero)
