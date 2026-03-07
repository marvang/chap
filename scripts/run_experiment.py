#!/usr/bin/env python3
"""
Run CTF experiments on multiple challenges

Usage:
    python scripts/run_experiment.py  # Use defaults from this file
    python scripts/run_experiment.py --chap --name "chap_enabled" --token-base 80000
    python scripts/run_experiment.py --no-chap --name "chap_disabled"
"""
import sys
import os
import time
import argparse
import subprocess
from datetime import datetime
import json
# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.experiment_utils.main_experiment_agent import run_experiment_agent
from src.experiment_utils.start_container import start_container
from src.experiment_utils.stop_container import stop_container
from src.experiment_utils.start_network import start_network
from src.experiment_utils.stop_network import stop_network
from src.experiment_utils.start_kali_container import start_kali_container
from src.experiment_utils.stop_kali_container import stop_kali_container
from src.experiment_utils.validate_flag import flag_match, get_expected_flag
from src.experiment_utils.key_validator import validate_rsa_key_match
from src.utils.discord_utils import (
    create_experiment_channel,
    send_experiment_start_message,
    send_experiment_complete_message,
    send_experiment_interrupted_message,
    send_experiment_error_message,
    send_challenge_start_message,
    send_challenge_complete_message,
    send_challenge_error_message,
    send_docker_connection_error_message
)


# ============================================================================
# EXPERIMENT CONFIGURATION
# ============================================================================

# Toggle between test and production configurations
TEST_RUN = False # Set to True only for test runs, OBS: gives agent solutions directly in custom instrucions, good for quick debugging

# Enable/disable per-challenge custom instructions. Recommended to keep True. check scripts/experiment_config files for details.
USE_CUSTOM_INSTRUCTIONS = True

# Import appropriate config based on TEST_RUN
if TEST_RUN:
    from scripts.experiment_config_test import CHALLENGE_CUSTOM_INSTRUCTIONS, DEFAULT_CUSTOM_INSTRUCTIONS
else:
    from scripts.experiment_config import CHALLENGE_CUSTOM_INSTRUCTIONS, DEFAULT_CUSTOM_INSTRUCTIONS

CTF_FLAG_PATH = "benchmark/machines/real-world/cve"
# Challenges to test (all VMs enabled for overnight runs)
CTF_CHALLENGES = [
    "vm0",
    "vm1",
    "vm2",
    "vm3",
    "vm4",
    "vm5",
    "vm6",
    "vm7",
    "vm8",
    "vm9",
    "vm10",
]

# ============================================================================
# DEFAULT VALUES (can be overridden via CLI)
# ============================================================================
MODEL_NAME = "openai/gpt-5.1-codex-mini"
CHAP_ENABLED = False
MAX_ITERATIONS = 220
COMMAND_TIMEOUT = 200
MAX_COST = 3
MAX_OUTPUT_LENGTH = 12000 

# CHAP prompt token thresholds (only used if CHAP enabled)
# Threshold increases per agent: threshold = BASE + (agent_number * INCREMENT)
CHAP_TOKEN_LIMIT_BASE = 500
CHAP_TOKEN_LIMIT_INCREMENT = 5000

CHAP_AUTO_TRIGGER = True # If True, auto-trigger relay based on token limits; if False, only agent-initiated relay allowed
CHAP_MIN_ITERATIONS_FOR_RELAY = 30 # Minimum iterations before manual relay is allowed

DISCORD_NOTIFICATIONS_ENABLED = True # Set to False, to enable you need to set DISCORD_MAIN_BOT_TOKEN and DISCORD_GUILD_ID in .env which you can get from your Discord developer portal after creating an application and bot

# Architecture-specific prompt: False = macOS/aarch64 (Kali emulates targets), True = Ubuntu/amd64 (native execution)
USE_AMD64_PROMPT = False

KALI_CONTAINER_NAME = "ctf-agent-kali"
SERVICE_STARTUP_DELAY = 30

RESULTS_DIR = "./results"
EXPERIMENT_SET_NAME = "default"


# ============================================================================
# CLI ARGUMENT PARSING
# ============================================================================
def parse_args():
    """Parse command line arguments to override defaults."""
    parser = argparse.ArgumentParser(description="Run CTF experiments")
    
    # CHAP toggle
  
    chap_group = parser.add_mutually_exclusive_group()
    chap_group.add_argument("--chap", dest="chap_enabled", action="store_true", 
                           help="Enable CHAP (default)")
    chap_group.add_argument("--no-chap", dest="chap_enabled", action="store_false",
                           help="Disable CHAP")
    parser.set_defaults(chap_enabled=None)  # None means use file default
    
    # Other overrides
    parser.add_argument("--name", type=str, default=None,
                       help="Experiment set name (for results folder)")
    parser.add_argument("--token-base", type=int, default=None,
                       help="Override CHAP token limit base")
    parser.add_argument("--model", type=str, default=None,
                       help="Model name")
    parser.add_argument("--token-increment", type=int, default=None,
                       help="Override CHAP token limit increment per relay")
    
    # Auto-trigger toggle (only relevant when CHAP enabled)
    auto_trigger_group = parser.add_mutually_exclusive_group()
    auto_trigger_group.add_argument("--auto-trigger", dest="auto_trigger", action="store_true",
                                    help="Enable auto-trigger relay based on token limits (default)")
    auto_trigger_group.add_argument("--no-auto-trigger", dest="auto_trigger", action="store_false",
                                    help="Disable auto-trigger, only agent-initiated relay allowed")
    parser.set_defaults(auto_trigger=None)  # None means use file default

    return parser.parse_args()


def apply_cli_overrides(args):
    """Apply CLI arguments to global config variables."""
    global CHAP_ENABLED, EXPERIMENT_SET_NAME, CHAP_TOKEN_LIMIT_BASE
    global MODEL_NAME, CHAP_TOKEN_LIMIT_INCREMENT, CHAP_AUTO_TRIGGER

    if args.chap_enabled is not None:
        CHAP_ENABLED = args.chap_enabled
    if args.name is not None:
        EXPERIMENT_SET_NAME = args.name
    if args.token_base is not None:
        CHAP_TOKEN_LIMIT_BASE = args.token_base
    if args.model is not None:
        MODEL_NAME = args.model
    if args.token_increment is not None:
        CHAP_TOKEN_LIMIT_INCREMENT = args.token_increment
    if args.auto_trigger is not None:
        CHAP_AUTO_TRIGGER = args.auto_trigger

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_custom_instructions_for_challenge(challenge_name: str) -> str:
    """Get custom instructions for a specific challenge."""
    if not USE_CUSTOM_INSTRUCTIONS:
        return ""
    return CHALLENGE_CUSTOM_INSTRUCTIONS.get(challenge_name, DEFAULT_CUSTOM_INSTRUCTIONS)

def get_git_commit_hash() -> str | None:
    """Get current git commit hash for reproducibility. Returns None if unavailable."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None

def save_results(results: list, results_dir: str, experiment_dir: str | None = None, experiment_timestamp: str | None = None, termination_reason: str | None = None):
    """Save experiment results to structured per-challenge files."""
    os.makedirs(results_dir, exist_ok=True)
    timestamp = experiment_timestamp or datetime.now().strftime('%Y%m%d_%H%M%S')
    if experiment_dir is None:
        experiment_dir = os.path.join(results_dir, f"experiment_{timestamp}")
    os.makedirs(experiment_dir, exist_ok=True)

    custom_instructions_map: dict[str, str] = {}
    if USE_CUSTOM_INSTRUCTIONS:
        custom_instructions_map = {
            challenge: get_custom_instructions_for_challenge(challenge)
            for challenge in CTF_CHALLENGES
        }
    experiment_metadata = {
        "timestamp": timestamp,
        "git_commit_hash": get_git_commit_hash(),
        "ctf_flag_path": CTF_FLAG_PATH,
        "ctf_challenges": CTF_CHALLENGES,
        "model": MODEL_NAME,
        "chap_enabled": CHAP_ENABLED,
        "challenge_count": len(CTF_CHALLENGES),
        "completed_challenges": len(results),
        "max_iterations": MAX_ITERATIONS,
        "command_timeout_seconds": COMMAND_TIMEOUT,
        "max_cost": MAX_COST,
        "test_run": TEST_RUN,
        "use_custom_instructions": USE_CUSTOM_INSTRUCTIONS,
        "custom_instructions_by_challenge": custom_instructions_map,
        "chap_token_limit_base": CHAP_TOKEN_LIMIT_BASE,
        "chap_token_limit_increment": CHAP_TOKEN_LIMIT_INCREMENT,
        "chap_auto_trigger": CHAP_AUTO_TRIGGER,
        "chap_min_iterations_for_relay": CHAP_MIN_ITERATIONS_FOR_RELAY,
        "service_startup_delay_seconds": SERVICE_STARTUP_DELAY,
        "experiment_set_name": EXPERIMENT_SET_NAME,
        "discord_notifications_enabled": DISCORD_NOTIFICATIONS_ENABLED,
        "kali_container_name": KALI_CONTAINER_NAME,
        "results_dir": os.path.abspath(results_dir),
        "termination_reason": termination_reason or "unknown",
        "use_amd64_prompt": USE_AMD64_PROMPT,
    }

    for result in results:
        challenge_dir = os.path.join(experiment_dir, result['challenge_name'])
        os.makedirs(challenge_dir, exist_ok=True)

        # Save summary data for the challenge (without the heavy session log)
        # Note: custom_instructions available in experiment_summary.json under custom_instructions_by_challenge
        challenge_summary = {k: v for k, v in result.items() if k not in {"session", "prompt_snapshots"}}
        challenge_path = os.path.join(challenge_dir, "summary.json")
        with open(challenge_path, "w") as f:
            json.dump(challenge_summary, f, indent=2)

        # Save full session data with command/output history
        session_data = result.get("session")
        if session_data:
            session_path = os.path.join(challenge_dir, "session.json")
            with open(session_path, "w") as f:
                json.dump(session_data, f, indent=2)

        # Save prompt snapshots for reproducibility
        prompt_snapshots = result.get("prompt_snapshots")
        if prompt_snapshots:
            chap_enabled_raw = prompt_snapshots.get("chap_enabled", False)
            if isinstance(chap_enabled_raw, str):
                chap_enabled = chap_enabled_raw.strip().lower() == "true"
            else:
                chap_enabled = bool(chap_enabled_raw)

            initial_messages_raw = prompt_snapshots.get("initial_messages") or []
            system_prompt = None
            initial_messages = []
            for message in initial_messages_raw:
                if isinstance(message, dict) and message.get("role") == "system":
                    system_prompt = message.get("content")
                    continue
                initial_messages.append(message)

            challenge_name = prompt_snapshots.get("challenge_name") or result.get("challenge_name")
            chap_auto_trigger = prompt_snapshots.get("chap_auto_trigger", True)  # Default True for backwards compat
            # Note: custom_instructions available in experiment_summary.json, chap_prompt already in system_prompt
            prompt_payload = {
                "experiment_id": prompt_snapshots.get("experiment_id"),
                "challenge_name": challenge_name,
                "model_name": prompt_snapshots.get("model_name"),
                "chap_enabled": chap_enabled,
                "chap_auto_trigger": chap_auto_trigger,
                "system_prompt": system_prompt,
                "initial_messages": initial_messages,
            }

            if chap_enabled:
                if prompt_snapshots.get("protocol_generator_system_prompt") is not None:
                    prompt_payload["protocol_generator_system_prompt"] = prompt_snapshots.get("protocol_generator_system_prompt")
                prompt_payload["relay_initial_messages"] = prompt_snapshots.get("relay_initial_messages", [])

            prompt_path = os.path.join(challenge_dir, "used_prompts.json")
            with open(prompt_path, "w") as f:
                json.dump(prompt_payload, f, indent=2)
                f.write("\n")

    # Write overall experiment summary for quick inspection
    summary_path = os.path.join(experiment_dir, "experiment_summary.json")
    with open(summary_path, "w") as f:
        json.dump({"metadata": experiment_metadata}, f, indent=2)

    print(f"💾 Results saved to {experiment_dir}")


# ============================================================================
# MAIN EXPERIMENT RUNNER
# ============================================================================

def main():
    """Run experiments on all CTF challenges"""
    # Parse CLI args and apply overrides
    args = parse_args()
    apply_cli_overrides(args)
    
    print("="*80)
    print("CTF EXPERIMENT SUITE")
    print("="*80)
    print(f"Model: {MODEL_NAME}")
    print(f"CHAP: {'Enabled' if CHAP_ENABLED else 'Disabled'}")
    if CHAP_ENABLED:
        print(f"CHAP Token Base: {CHAP_TOKEN_LIMIT_BASE}")
        print(f"CHAP Auto-Trigger: {'Enabled' if CHAP_AUTO_TRIGGER else 'Disabled'}")
    print(f"Challenges: {len(CTF_CHALLENGES)}")
    print(f"Max iterations: {MAX_ITERATIONS}")
    print(f"Max cost per challenge: ${MAX_COST}")
    print(f"Experiment name: {EXPERIMENT_SET_NAME}")
    print("="*80)

    print("\n🌐 Ensuring Docker network is available...")
    start_network()

    results = []
    experiment_id = datetime.now().strftime('%Y%m%d_%H%M%S')
    discord_experiment_id = f"{EXPERIMENT_SET_NAME}-{experiment_id}" if EXPERIMENT_SET_NAME else experiment_id
    results_dir = os.path.join(RESULTS_DIR, EXPERIMENT_SET_NAME) if EXPERIMENT_SET_NAME else RESULTS_DIR
    experiment_dir = os.path.join(results_dir, f"experiment_{experiment_id}")
    os.makedirs(experiment_dir, exist_ok=True)
    termination_reason = "in_progress"
    save_results(results, results_dir, experiment_dir, experiment_id, termination_reason)
    total_challenges = len(CTF_CHALLENGES)

    channel_id = None
    if DISCORD_NOTIFICATIONS_ENABLED:
        channel_id = create_experiment_channel(discord_experiment_id)
        if not channel_id:
            print("⚠️  Failed to create Discord channel. Continuing without Discord notifications.")
            print("   To enable: set DISCORD_MAIN_BOT_TOKEN, DISCORD_GUILD_ID in .env")
        else:
            send_experiment_start_message(
                channel_id=channel_id,
                experiment_id=experiment_id,
                config={
                    "model": MODEL_NAME,
                    "chap_enabled": CHAP_ENABLED,
                    "challenges": CTF_CHALLENGES,
                    "max_iterations": MAX_ITERATIONS,
                    "max_cost": MAX_COST
                }
            )

    try:
        for idx, challenge in enumerate(CTF_CHALLENGES, 1):
            print(f"\n{'='*80}")
            print(f"Challenge {idx}/{total_challenges}: {challenge}")
            print(f"{'='*80}")

            send_challenge_start_message(
                channel_id=channel_id,
                challenge=challenge,
                index=idx,
                total=total_challenges
            )

            try:
                # Start vulnerable container
                print(f"\n📦 Starting vulnerable container: {challenge}")
                target_ip = start_container(challenge)
                print(f"✅ Container started at {target_ip}")

                current_time = datetime.now().strftime("%H:%M:%S %Y-%m-%d")
                print(f"🕒 Current time: {current_time}")

                # Wait for service to initialize (emulated amd64 can be slow)
                print(f"⏳ Waiting {SERVICE_STARTUP_DELAY}s for service to initialize...")
                time.sleep(SERVICE_STARTUP_DELAY)
                print(f"✅ Proceeding with challenge")

                # Start Kali container for clean environment
                if not start_kali_container(KALI_CONTAINER_NAME):
                    send_docker_connection_error_message(
                        channel_id=channel_id,
                        container_name=KALI_CONTAINER_NAME,
                        context={
                            "challenge": challenge,
                            "experiment_id": experiment_id
                        }
                    )
                    raise Exception("Failed to start Kali container")

                # Get expected flags
                if challenge == "vm10":
                    # Special case for vm10: Read entire file as single flag (RSA private key)
                    flag_file_path = os.path.join(CTF_FLAG_PATH, challenge, "flag.txt")
                    try:
                        with open(flag_file_path, 'r') as f:
                            full_key = f.read().strip()
                        expected_flags = [full_key]
                        print(f"🔑 Loaded RSA private key ({len(full_key)} bytes)")
                    except FileNotFoundError:
                        print(f"⚠️ Flag file not found: {flag_file_path}")
                        expected_flags = None
                else:
                    # Standard multi-line flag support for all other challenges
                    expected_flags = get_expected_flag(
                        challenge_name=challenge,
                        ctf_flag_path=CTF_FLAG_PATH,
                    )

                if expected_flags:
                    # Print flag info (except for vm10 which already printed)
                    if challenge != "vm10":
                        if len(expected_flags) == 1:
                            print(f"🏁 Expected flag: {expected_flags[0]}")
                        else:
                            print(f"🏁 Expected flags: {', '.join(expected_flags)}")
                else:
                    print(f"⚠️ No expected flag available for validation")
                    break

                # Run experiment
                result = run_experiment_agent(
                    experiment_id=f"{experiment_id}",
                    experiment_loop_iteration=idx,
                    total_loop_iterations=total_challenges,
                    target_ip=target_ip,
                    challenge_name=challenge,
                    model_name=MODEL_NAME,
                    chap_enabled=CHAP_ENABLED,
                    chap_auto_trigger=CHAP_AUTO_TRIGGER,
                    max_iterations=MAX_ITERATIONS,
                    command_timeout_seconds=COMMAND_TIMEOUT,
                    max_cost=MAX_COST,
                    max_output_length=MAX_OUTPUT_LENGTH,
                    chap_token_limit_base=CHAP_TOKEN_LIMIT_BASE,
                    chap_token_limit_increment=CHAP_TOKEN_LIMIT_INCREMENT,
                    chap_min_iterations_for_relay=CHAP_MIN_ITERATIONS_FOR_RELAY,
                    kali_container_name=KALI_CONTAINER_NAME,
                    custom_instructions=get_custom_instructions_for_challenge(challenge),
                    channel_id=channel_id,
                    use_amd64_prompt=USE_AMD64_PROMPT
                )

                # Ensure challenge_name is in result
                result['challenge_name'] = challenge

                # Validate flag
                captured_flag = result.get('flag_captured') or ""

                # Special case for vm10: cryptographic key validation
                if challenge == "vm10":
                    # For vm10, expected_flags[0] contains the full private key
                    flag_valid = validate_rsa_key_match(captured_flag, expected_flags[0])
                else:
                    # Standard string-based validation for other challenges
                    flag_valid = flag_match(found_flag=captured_flag, ground_truth_flags=expected_flags)

                result['flag_valid'] = flag_valid
                result['expected_flags'] = expected_flags

                # Store result
                results.append(result)

                # Print result summary
                print(f"\n{'='*80}")
                print(f"RESULT: {challenge}")
                print(f"{'='*80}")
                print(f"Flag captured: {result['flag_captured']}")
                if expected_flags:
                    print(f"Flag valid: {'✅' if result['flag_valid'] else '❌'} {result['flag_valid']}")
                print(f"Iterations: {result['iterations']}")
                print(f"Relay count: {result['relay_count']}")
                print(f"Cost: ${result['total_cost']:.4f}")
                print(f"Time: {result['total_time']:.1f}s")
                print(f"Stopping reason: {result['stopping_reason']}")
                if result['error']:
                    print(f"Error: {result['error']}")
                print(f"{'='*80}")

                send_challenge_complete_message(
                    channel_id=channel_id,
                    challenge=challenge,
                    result=result
                )

            except Exception as e:
                print(f"\n❌ Error running experiment for {challenge}: {e}")
                import traceback
                traceback.print_exc()

                send_challenge_error_message(
                    channel_id=channel_id,
                    challenge=challenge,
                    error_msg=str(e),
                    experiment_id=experiment_id
                )

                results.append({
                    "challenge_name": challenge,
                    "flag_captured": None,
                    "prompt_snapshots": None,
                    "session": None,
                    "iterations": 0,
                    "relay_count": 0,
                    "relay_triggers": [],
                    "error": str(e),
                    "llm_error_details": None,
                    "cost_limit_reached": False,
                    "iteration_limit_reached": False,
                    "stopping_reason": "exception_error",
                    "total_cost": 0.0,
                    "total_time": 0.0,
                    "flag_valid": False,
                    "expected_flags": None,
                })

            finally:
                # Cleanup: Stop Kali container
                print(f"\n🧹 Cleaning up...")
                stop_kali_container(KALI_CONTAINER_NAME)

                # Stop vulnerable container
                print(f"🧹 Stopping vulnerable container: {challenge}")
                stop_container(challenge)

            save_results(results, results_dir, experiment_dir, experiment_id, termination_reason)

    except KeyboardInterrupt:
        termination_reason = "interrupted_by_user"
        print("\n⚠️ Experiment interrupted by user. Saving partial results...")
        save_results(results, results_dir, experiment_dir, experiment_id, termination_reason)

        send_experiment_interrupted_message(
            channel_id=channel_id,
            partial_results=len(results),
            total_challenges=total_challenges
        )

    except Exception as e:
        termination_reason = f"error: {e}"
        print(f"\n❌ Experiment aborted due to unexpected error: {e}")
        import traceback
        traceback.print_exc()
        save_results(results, results_dir, experiment_dir, experiment_id, termination_reason)

        send_experiment_error_message(
            channel_id=channel_id,
            error_msg=str(e),
            partial_results=len(results)
        )

    else:
        termination_reason = "completed"
        # Save results
        save_results(results, results_dir, experiment_dir, experiment_id, termination_reason)

        # Print final summary
        print("\n" + "="*80)
        print("EXPERIMENT SUITE COMPLETE")
        print("="*80)
        print(f"Total challenges: {len(CTF_CHALLENGES)}")
        print(f"Successful: {sum(1 for r in results if r.get('flag_valid', False))}")
        print(f"Failed: {sum(1 for r in results if not r.get('flag_valid', False))}")
        print(f"Total cost: ${sum(r.get('total_cost', 0) for r in results):.4f}")
        print(f"Total time: {sum(r.get('total_time', 0) for r in results):.1f}s")

        # Flag validation summary
        valid_flags = sum(1 for r in results if r.get('flag_valid', False))
        print(f"\nFlag validation:")
        print(f"  Valid flags captured: {valid_flags}/{len(CTF_CHALLENGES)}")

        print("="*80)

        send_experiment_complete_message(
            channel_id=channel_id,
            results=results,
            metadata={
                "total_challenges": len(CTF_CHALLENGES),
                "successful": sum(1 for r in results if r.get('flag_valid', False)),
                "failed": sum(1 for r in results if not r.get('flag_valid', False)),
                "total_cost": sum(r.get('total_cost', 0) for r in results),
                "total_time": sum(r.get('total_time', 0) for r in results),
                "valid_flags": valid_flags,
                "termination_reason": termination_reason
            }
        )

    print("\n🛑 Stopping Docker network...")
    stop_network()
    print("Exit.")

if __name__ == "__main__":
    main()
