"""
CTF Agent - Experiment Function
Automated agent runner for CTF experiments (no user interaction)
"""

import os
import time
import json
import copy
from typing import Optional, Dict, Any
from dotenv import load_dotenv
from src.llm_utils.openrouter import call_openrouter_with_history
from src.llm_utils.prompt_builder import build_initial_messages
from src.llm_utils import prompts
from src.utils.state_manager import (
    create_session,
    update_session_tokens,
    add_session_command,
)
from src.utils.workspace import cleanup_workspace
from src.utils.docker_exec import execute_command, cleanup_tmux_session, get_container_ips
from src.utils.docker_utils import connect_to_docker
from src.chap_utils.relay_handler import trigger_relay_handoff
from src.chap_utils.protocol_generator import PROTOCOL_GENERATOR_SYSTEM_PROMPT
from src.utils.discord_utils import (
    send_auto_relay_message,
    send_manual_relay_message,
    send_llm_error_message,
    send_empty_command_stop_message,
)

# Workspace cleanup configuration
WORKSPACE_DIR = "./ctf-workspace"

APPROVED_FILES = [
]
FILES_TO_EMPTY = [
    "flags.txt",
]

# Empty command retry configuration
MAX_EMPTY_COMMAND_RETRIES = 5

#"temperature": 1, # Not available for openai models
#"seed": 1, # not available for anthropic models 
# * using openrouter, might be available in using other providers
def run_experiment_agent(
    experiment_id: str, # info purposes
    experiment_loop_iteration: int, # info purposes
    total_loop_iterations: int, # info purposes
    target_ip: str,
    challenge_name: str, # info purposes
    model_name: str,
    chap_enabled: bool,
    chap_auto_trigger: bool,
    max_iterations: int,
    command_timeout_seconds: int,
    max_cost: float,
    max_output_length: int,
    chap_token_limit_base: int,
    chap_token_limit_increment: int,
    chap_min_iterations_for_relay: int = 30,
    seed: Optional[int] = None, # currently not used
    temperature: Optional[float] = 1.0, # currently not used
    kali_container_name: str = "CHAP-kali-linux",
    custom_instructions: str = "",
    channel_id: Optional[str] = None,
    use_amd64_prompt: bool = False
) -> Dict[str, Any]:
    """
    Run CTF agent in experiment mode (no user interaction)

    Args:
        target_ip: IP address of target container (e.g., "192.168.5.0")
        challenge_name: Name of challenge (e.g., "vm0")
        model_name: OpenRouter model identifier
        chap_enabled: Whether to enable CHAP (Context Relay Protocol)
        chap_auto_trigger: Whether to auto-trigger relay based on token limits (only used if chap_enabled)
        max_iterations: Maximum number of iterations before stopping
        command_timeout: Timeout in seconds for each command execution
        max_cost: Cost threshold to stop at (in USD)
        max_output_length: Maximum output characters to retain for LLM context
        token_limit_base: Starting token limit before first relay
        token_limit_increment: Additional tokens allowed per agent number
        chap_min_iterations_for_relay: Minimum iterations before manual relay is allowed
        seed: Random seed for reproducibility (optional)
        temperature: LLM temperature parameter
        custom_instructions: Additional instructions for the agent
        channel_id: Discord channel for webhook notifications (optional)

    Returns:
        {
            "flag_captured": str or None,
            "session": session_dict,
            "iterations": int,
            "challenge_name": str,
            "target_ip": str,
            "error": str or None,
            "cost_limit_reached": bool,
            "iteration_limit_reached": bool,
            "stopping_reason": str or None,
            "total_time": float,
            "total_cost": float
        }
    """
    load_dotenv()

    print(f"\n{'='*60}")
    print(f"🏴‍☠️  Experiment ID: {experiment_id}")
    print(f"🔁 Iteration: {experiment_loop_iteration} / {total_loop_iterations}")
    print(f"🎯 CTF Challenge: {challenge_name}")
    print(f"📍 Target IP: {target_ip}")
    print(f"🤖 Model: {model_name}")
    print(f"🔄 CHAP: {'Enabled' if chap_enabled else 'Disabled'}")
    print(f"🎲 Seed: {seed}")
    print(f"📊 Max Iterations: {max_iterations}")
    print('='*60)

    # Clean up workspace files from previous runs (MUST succeed to prevent flag contamination)
    if not cleanup_workspace(WORKSPACE_DIR, APPROVED_FILES, FILES_TO_EMPTY, auto_confirm=True):
        return {
            "flag_captured": None,
            "prompt_snapshots": None,
            "session": None,
            "iterations": 0,
            "relay_count": 0,
            "relay_triggers": [],
            "error": "Workspace cleanup failed - aborting to prevent flag contamination",
            "llm_error_details": None,
            "cost_limit_reached": False,
            "iteration_limit_reached": False,
            "stopping_reason": "workspace_cleanup_failed",
            "total_time": 0.0,
            "total_cost": 0.0
        }

    # Connect to kali container
    _, container = connect_to_docker(kali_container_name)
    if container is None:
        return {
            "flag_captured": None,
            "prompt_snapshots": None,
            "session": None,
            "iterations": 0,
            "relay_count": 0,
            "relay_triggers": [],
            "error": "Failed to connect to Docker container",
            "llm_error_details": None,
            "cost_limit_reached": False,
            "iteration_limit_reached": False,
            "stopping_reason": "docker_connection_error",
            "total_time": 0.0,
            "total_cost": 0.0
        }

    # Get agent IP addresses from container (no VPN)
    agent_ips = get_container_ips(container, use_vpn=False)
    print(f"\n🔍 Agent IP: {', '.join(agent_ips)}")

    # Create session
    session = create_session(model=model_name, crp_enabled=chap_enabled)

    # Build initial messages (no VPN, local container mode)
    messages = build_initial_messages(
        use_vpn=False,
        target_info=target_ip,
        use_chap=chap_enabled,
        custom_instructions=custom_instructions,
        agent_ips=agent_ips,
        use_amd64_prompt=use_amd64_prompt
    )

    prompt_snapshots = {
        "experiment_id": experiment_id,
        "challenge_name": challenge_name,
        "model_name": model_name,
        "chap_enabled": chap_enabled,
        "chap_auto_trigger": chap_auto_trigger,
        "initial_messages": copy.deepcopy(messages),
        "relay_initial_messages": []
    }

    if chap_enabled:
        prompt_snapshots["chap_prompt"] = prompts.CHAP
        prompt_snapshots["protocol_generator_system_prompt"] = PROTOCOL_GENERATOR_SYSTEM_PROMPT

    iteration = 0 # track iterations
    relay = 0 # track relays
    last_relay_iteration = 0  # Track iteration when last relay occurred (for minimum iteration check)
    chap_80_percent_warning_shown = False  # Track if 80% token warning has been shown (reset after each relay)
    session_start_time = time.time()

    # Track stopping reasons
    cost_limit_reached = False
    iteration_limit_reached = False
    error_message = None
    llm_error_details = None  # Detailed LLM API error info (code, message, metadata)
    empty_command_count = 0  # Track consecutive empty commands
    stopping_reason = None  # Track why the experiment stopped

    # Main interaction loop
    while True:
        print(f"\n{'='*40}")
        iteration_header = f"Iteration {iteration + 1}"
        if chap_enabled:
            iteration_header += f" (CHAP Agent #{session['agent_number']})"
        print(iteration_header)
        print('='*40)

        # Cost threshold check - prompt user if exceeded
        current_session_cost = session["metrics"]["total_cost"]
        if current_session_cost >= max_cost:
            print(f"\n⚠️  Cost limit reached: ${current_session_cost:.4f} >= ${max_cost:.2f}")
            print("Stopping experiment due to cost limit (non-interactive mode)...")
            cost_limit_reached = True
            stopping_reason = "cost_limit"
            break

        # Iteration threshold check - stop if exceeded
        if iteration >= max_iterations:
            print(f"\n⚠️  Iteration limit reached: {iteration} > {max_iterations}")
            print("Stopping experiment...")
            iteration_limit_reached = True
            stopping_reason = "iteration_limit"
            break

        # LLM call (Note: seed and temperature are commented out in openrouter.py)
        try:
            reasoning, shell_command, usage, extended_reasoning = call_openrouter_with_history(
                messages=messages,
                model_name=model_name,
            )
            # TODO: Pass seed and temperature when OpenRouter adds support for all models
        except Exception as e:
            print(f"❌ LLM API error: {e}")

            # Try to parse structured error details from the exception message
            error_str = str(e)
            if "OpenRouter API error:" in error_str:
                try:
                    # Extract JSON from "OpenRouter API error: {...}"
                    json_start = error_str.index("{") 
                    llm_error_details = json.loads(error_str[json_start:])
                except (ValueError, json.JSONDecodeError):
                    llm_error_details = {"raw_error": error_str}
            else:
                llm_error_details = {"raw_error": error_str}

            send_llm_error_message(
                channel_id=channel_id,
                error_msg=str(e),
                context={
                    "challenge": challenge_name,
                    "iteration": iteration,
                    "model": model_name,
                    "experiment_id": experiment_id
                }
            )

            error_message = f"LLM API error: {str(e)}"
            stopping_reason = "llm_error"
            break

        # Display LLM response
        if extended_reasoning:
            # Truncate long extended reasoning for display
            display_extended = extended_reasoning[:500]
            if len(extended_reasoning) > 500:
                display_extended += "..."
            print(f"\n💭 Internal Reasoning:\n<thinking>\n{display_extended}\n</thinking>")
        print(f"\n🧠 Reasoning: {reasoning}")
        print(f"\n💻 Command: {shell_command}")

        # Track token usage
        prompt_tokens = 0
        token_limit_for_agent = 0
        token_usage_percentage = 0.0

        if usage:
            update_session_tokens(session, usage)

            # Calculate token metrics for CHAP (used for status display and auto-trigger)
            if chap_enabled:
                prompt_tokens = usage.get('prompt_tokens', 0)
                token_limit_for_agent = chap_token_limit_base + (session["agent_number"] * chap_token_limit_increment)
                if token_limit_for_agent > 0:
                    token_usage_percentage = (prompt_tokens / token_limit_for_agent) * 100

            # Check if input prompt exceeded threshold (CHAP only, when auto-trigger enabled)
            if chap_enabled and chap_auto_trigger and prompt_tokens >= token_limit_for_agent:
                    print(f"\n⚠️  Auto-triggering relay: Input prompt exceeded threshold!")
                    print(f"💬 Prompt tokens: {prompt_tokens:,} / {token_limit_for_agent:,}")
                    print(f"🤖 Agent {session['agent_number']} handing off...")

                    # Update session time before relay
                    session['metrics']['total_time'] = time.time() - session_start_time

                    messages = trigger_relay_handoff(
                        session=session,
                        messages=messages,
                        model_name=model_name,
                        use_vpn=False,
                        target_info=target_ip,
                        custom_instructions=custom_instructions,
                        current_iteration=iteration,
                        agent_ips=agent_ips,
                        use_amd64_prompt=use_amd64_prompt
                    )
                    relay += 1
                    if chap_enabled:
                        # Save only relay_number and user message content (not full messages with system prompt)
                        user_message = next((m for m in messages if m.get("role") == "user"), None)
                        prompt_snapshots["relay_initial_messages"].append({
                            "relay_number": relay,
                            "user_content": user_message.get("content") if user_message else None
                        })

                    # Track relay trigger
                    if 'relay_triggers' not in session:
                        session['relay_triggers'] = []
                    session['relay_triggers'].append({
                        'relay_number': relay,
                        'trigger_type': 'auto',
                        'iteration': iteration,
                        'reason': 'prompt_token_threshold',
                        'prompt_tokens': prompt_tokens,
                        'token_limit': token_limit_for_agent
                    })

                    send_auto_relay_message(
                        channel_id=channel_id,
                        relay_data={
                            "agent_number": session['agent_number'] - 1,
                            "prompt_tokens": prompt_tokens,
                            "token_threshold": token_limit_for_agent,
                            "iteration": iteration,
                            "challenge": challenge_name,
                            "experiment_id": experiment_id
                        }
                    )

                    # Reset per-agent state for new agent
                    last_relay_iteration = iteration
                    chap_80_percent_warning_shown = False

                    continue

        # Add assistant response to history
        assistant_message = {
            "role": "assistant",
            "content": json.dumps({"reasoning": reasoning, "shell_command": shell_command})
        }
        messages.append(assistant_message)
        
        # Check for empty command
        if not shell_command.strip():
            empty_command_count += 1

            if empty_command_count < MAX_EMPTY_COMMAND_RETRIES:
                print(f"\n⚠️  No command provided - retrying ({empty_command_count}/{MAX_EMPTY_COMMAND_RETRIES})...")

                # Final warning on penultimate attempt
                if empty_command_count == MAX_EMPTY_COMMAND_RETRIES - 1:
                    messages.append({
                        "role": "user",
                        "content": (
                            f"FINAL WARNING: {empty_command_count} consecutive empty commands. One more will stop the experiment.\n"
                            "If your complex commands are failing to parse, output a simple command like 'pwd' to reset the counter and continue.\n"
                            "Respond with ONLY a JSON object of the form:\n"
                            '{"reasoning": "...", "shell_command": "..."}\n'
                            'If you intend to stop, respond with "exit".'
                        ),
                    })
                else:
                    messages.append({
                        "role": "user",
                        "content": (
                            "Your last response yielded no command after parsing, perhaps it did not contain a valid JSON object with keys "
                            '"reasoning" and "shell_command", so parsing failed.\n'
                            "Respond again with ONLY a JSON object of the form:\n"
                            '{"reasoning": "...", "shell_command": "..."}'
                        ),
                    })
                continue

            print(f"\n⚠️  No command provided {MAX_EMPTY_COMMAND_RETRIES} times in a row - stopping")
            error_message = f"Agent provided empty command {MAX_EMPTY_COMMAND_RETRIES} times"
            stopping_reason = "empty_command"

            send_empty_command_stop_message(
                channel_id=channel_id,
                context={
                    "challenge": challenge_name,
                    "iteration": iteration + 1,
                    "experiment_id": experiment_id
                }
            )

            break
        
        # Reset retry flag on successful command
        empty_command_count = 0

        # Check for exit command
        shell_cmd_clean = shell_command.strip()
        if shell_cmd_clean.lower() in ["exit", "quit", "terminate"]:
            print("\n✅ Agent requested termination")
            stopping_reason = "agent_exit"
            break

        # Check for relay command
        if shell_cmd_clean.lower() == "relay":
            if not chap_enabled:
                print("\n⚠️  CRP not enabled. Cannot trigger relay.")
                error_message = "Relay requested but CHAP not enabled"
                stopping_reason = "relay_without_chap"
                break

            # Check minimum iteration requirement (iterations since last relay, not absolute count)
            iterations_since_relay = iteration - last_relay_iteration
            if iterations_since_relay < chap_min_iterations_for_relay:
                iterations_remaining = chap_min_iterations_for_relay - iterations_since_relay
                print(f"\n⚠️  Relay rejected: Too early. Need {iterations_remaining} more iterations.")
                rejection_message = {
                    "role": "user",
                    "content": f"CHAP: Relay rejected - too early to relay. Minimum {chap_min_iterations_for_relay} iterations required since last relay. Current agent iterations: {iterations_since_relay}. Continue for {iterations_remaining} more iterations."
                }
                messages.append(rejection_message)
                continue

            # Update session time before relay (same as auto-trigger)
            session['metrics']['total_time'] = time.time() - session_start_time

            messages = trigger_relay_handoff(
                session=session,
                messages=messages,
                model_name=model_name,
                use_vpn=False,
                target_info=target_ip,
                custom_instructions=custom_instructions,
                current_iteration=iteration,
                agent_ips=agent_ips,
                use_amd64_prompt=use_amd64_prompt
            )
            relay += 1
            if chap_enabled:
                # Save only relay_number and user message content (not full messages with system prompt)
                user_message = next((m for m in messages if m.get("role") == "user"), None)
                prompt_snapshots["relay_initial_messages"].append({
                    "relay_number": relay,
                    "user_content": user_message.get("content") if user_message else None
                })
            # Track that this was an agent-initiated relay
            if 'relay_triggers' not in session:
                session['relay_triggers'] = []
            session['relay_triggers'].append({
                'relay_number': relay,
                'trigger_type': 'manual',
                'iteration': iteration,
                'reason': 'agent_command'
            })

            send_manual_relay_message(
                channel_id=channel_id,
                relay_data={
                    "agent_number": session['agent_number'] - 1,  # Previous agent that triggered relay
                    "iteration": iteration,
                    "challenge": challenge_name,
                    "experiment_id": experiment_id,
                    "reason": "Agent command"
                }
            )

            # Reset per-agent state for new agent
            last_relay_iteration = iteration
            chap_80_percent_warning_shown = False

            continue

        # Command execution
        print(f"\n🤖 Executing...")
        success, output, exit_code = execute_command(container, shell_command, command_timeout_seconds)

        # Limit output for LLM context
        if len(output) > max_output_length:
            separator = "\n...\n"
            head_len = max_output_length // 2
            tail_len = max(max_output_length - head_len - len(separator), 0)
            truncated_output = output[:head_len]
            if tail_len:
                truncated_output += separator + output[-tail_len:]
            truncation_warning = f"[SYSTEM WARNING: Output truncated. Showing first {head_len} and last {tail_len} of {len(output)} characters]\n\n"
            llm_output = truncation_warning + truncated_output
        else:
            llm_output = output

        print(f"\n📤 Output:")
        print(llm_output)
        if not success:
            print(f"⚠️  Exit code: {exit_code}")

        # Add to session log with the same content sent to the LLM
        add_session_command(
            session, shell_command, llm_output, exit_code,
            reasoning, usage, session['agent_number'], model_name, extended_reasoning
        )

        # Add command result to chat history
        result_content = f"Command executed with exit code {exit_code}. Output:\n{llm_output}"

        # Show CHAP 80% warning ONCE when threshold is crossed
        if chap_enabled and token_limit_for_agent > 0:
            if not chap_80_percent_warning_shown and token_usage_percentage >= 80:
                result_content += f"\n\nCHAP: 80% of tokens used, auto-relay at 100%"
                chap_80_percent_warning_shown = True

        result_message = {
            "role": "user",
            "content": result_content
        }
        messages.append(result_message)
        
        # Increment iteration counter and update session metrics
        iteration += 1
        session["metrics"]["total_iterations"] = iteration

    # End of loop - finalize session
    session["metrics"]["total_time"] = time.time() - session_start_time

    # Clean up tmux session
    cleanup_tmux_session(container)

    # Check if flag was captured
    captured_flag = _read_captured_flag()

    # cleanup workspace after run
    cleanup_workspace(WORKSPACE_DIR, APPROVED_FILES, FILES_TO_EMPTY, auto_confirm=True)

    # Print summary
    print(f"\n{'='*60}")
    print(f"🏁 CTF Complete: {challenge_name}")
    print(f"⏱️  Time: {session['metrics']['total_time']:.1f}s")
    print(f"🔢 Iterations: {iteration}")
    print(f"💰 Cost: ${session['metrics']['total_cost']:.4f}")
    print(f"🛑 Stopping Reason: {stopping_reason}")
    print(f"🤖 Final Agent Number: {session['agent_number']}")
    print(f"🏴 Flag: {captured_flag if captured_flag else 'No flag detected/captured'}")
    if error_message:
        print(f"❌ Error: {error_message}")
    print('='*60)

    # Return results
    return {
        "flag_captured": captured_flag,
        "prompt_snapshots": prompt_snapshots,
        "session": session,
        "iterations": iteration,
        "relay_count": relay,
        "error": error_message,
        "llm_error_details": llm_error_details,
        "cost_limit_reached": cost_limit_reached,
        "iteration_limit_reached": iteration_limit_reached,
        "stopping_reason": stopping_reason,
        "total_time": session["metrics"]["total_time"],
        "total_cost": session["metrics"]["total_cost"],
    }


def _read_captured_flag() -> Optional[str]:
    """
    Read flag from workspace/flags.txt or workspace/flag.txt

    Returns:
        Entire file contents or None if empty/missing
    """
    for filename in ("flags.txt", "flag.txt"):
        flags_path = os.path.join(WORKSPACE_DIR, filename)
        if not os.path.exists(flags_path):
            continue

        try:
            with open(flags_path, 'r') as f:
                content = f.read().strip()

            if content:
                return content
        except Exception as e:
            print(f"⚠️  Error reading flag file {filename}: {e}")
            return None

    return None
