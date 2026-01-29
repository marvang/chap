"""
State manager for CTF Agent
Handles shared state for the CTF agent
"""

import json
import os
from typing import Dict, Any, Optional
from datetime import datetime

# Constants
TOKEN_STATE_FILE = "./ctf-logs/token_state.json"
SESSIONS_FILE = "./ctf-logs/sessions.json"
LLM_CALLS_LOG = "./ctf-logs/llm_calls_detailed.log"


def ensure_state_dir():
    """Create state directory if it doesn't exist"""
    os.makedirs("./ctf-logs", exist_ok=True)

def update_token_state(usage: Dict[str, Any], model: str) -> Dict[str, Any]:
    """Update running totals per model and save state."""
    ensure_state_dir()
    
    # Load current state
    if os.path.exists(TOKEN_STATE_FILE):
        try:
            with open(TOKEN_STATE_FILE, "r") as f:
                state = json.load(f)
        except (json.JSONDecodeError, ValueError):
            state = {"models": {}}
    else:
        state = {"models": {}}
    
    if "models" not in state:
        state["models"] = {}

    # Initialize model state if needed
    if model not in state["models"]:
        state["models"][model] = {
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_reasoning_tokens": 0,
            "total_cached_tokens": 0,
            "total_audio_tokens": 0,
            "total_tokens": 0,
            "total_cost": 0.0,
            "total_upstream_inference_cost": 0.0,
            "request_count": 0,
        }

    # Update totals
    model_state = state["models"][model]
    model_state["total_input_tokens"] += usage.get("prompt_tokens") or 0
    model_state["total_output_tokens"] += usage.get("completion_tokens") or 0
    model_state["total_reasoning_tokens"] += usage.get("completion_tokens_details", {}).get("reasoning_tokens") or 0
    model_state["total_cached_tokens"] += usage.get("prompt_tokens_details", {}).get("cached_tokens") or 0
    model_state["total_audio_tokens"] += usage.get("prompt_tokens_details", {}).get("audio_tokens") or 0
    model_state["total_tokens"] += usage.get("total_tokens") or 0
    model_state["total_cost"] += usage.get("cost") or 0.0
    model_state["total_upstream_inference_cost"] += usage.get("cost_details", {}).get("upstream_inference_cost") or 0.0
    model_state["request_count"] += 1

    # Save state
    with open(TOKEN_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)
    
    return model_state


# Session tracking functions
def create_session(model: str, crp_enabled: bool = False) -> Dict[str, Any]:
    """Create a new session with unique ID and initial state."""
    import uuid
    session = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "model": model,
        "commands": [],
        "metrics": {
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_tokens": 0,
            "total_reasoning_tokens": 0,
            "total_cached_tokens": 0,
            "total_audio_tokens": 0,
            "total_cost": 0.0,
            "total_upstream_inference_cost": 0.0,
            "total_iterations": 0,
            "total_time": 0.0
        },
        "crp_enabled": crp_enabled,
        "agent_number": 0,  # Start with agent 0
        "relay_protocols": []  # Accumulated relay protocols
    }
    return session


def update_session_tokens(session: Dict[str, Any], usage: Dict[str, Any]) -> None:
    """Update session token usage with new usage data."""
    session["metrics"]["total_input_tokens"] += usage.get("prompt_tokens") or 0
    session["metrics"]["total_output_tokens"] += usage.get("completion_tokens") or 0
    session["metrics"]["total_tokens"] += usage.get("total_tokens") or 0
    session["metrics"]["total_reasoning_tokens"] += usage.get("completion_tokens_details", {}).get("reasoning_tokens") or 0
    session["metrics"]["total_cached_tokens"] += usage.get("prompt_tokens_details", {}).get("cached_tokens") or 0
    session["metrics"]["total_audio_tokens"] += usage.get("prompt_tokens_details", {}).get("audio_tokens") or 0
    session["metrics"]["total_cost"] += usage.get("cost") or 0.0
    session["metrics"]["total_upstream_inference_cost"] += usage.get("cost_details", {}).get("upstream_inference_cost") or 0.0


def add_session_command(session: Dict[str, Any], command: str, output: str, exit_code: int, reasoning: str = "", usage: Optional[Dict[str, Any]] = None, agent_number: int = 0, model_name: str = "", extended_reasoning: str = "") -> None:
    """Add a command, its output, reasoning, token usage, agent number, and model to the session."""
    command_entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "agent_number": agent_number,
        "model_name": model_name,
        "extended_reasoning": extended_reasoning,
        "reasoning": reasoning,
        "command": command,
        "output": output,
        "exit_code": exit_code
    }

    # Add enhanced token and cost information if usage data is provided
    if usage:
        command_entry["tokens"] = {
            "input_tokens": usage.get("prompt_tokens") or 0,
            "output_tokens": usage.get("completion_tokens") or 0,
            "total_tokens": usage.get("total_tokens") or 0,
            "reasoning_tokens": usage.get("completion_tokens_details", {}).get("reasoning_tokens") or 0,
            "cached_tokens": usage.get("prompt_tokens_details", {}).get("cached_tokens") or 0,
            "audio_tokens": usage.get("prompt_tokens_details", {}).get("audio_tokens") or 0,
        }
        command_entry["cost"] = {
            "total_cost": usage.get("cost") or 0.0,
            "upstream_inference_cost": usage.get("cost_details", {}).get("upstream_inference_cost") or 0.0
        }

    session["commands"].append(command_entry)


def save_session(session: Dict[str, Any]) -> None:
    """Save session to sessions file, including any generated report."""
    ensure_state_dir()

    # Check for generated report in workspace
    report_path = "./ctf-workspace/reports.txt"
    if os.path.exists(report_path):
        try:
            with open(report_path, "r", encoding="utf-8") as f:
                report_content = f.read().strip()
                if report_content:
                    session["report"] = report_content
        except Exception as e:
            print(f"⚠️  Could not read report file: {e}")

    # Load existing sessions
    if os.path.exists(SESSIONS_FILE):
        try:
            with open(SESSIONS_FILE, "r") as f:
                sessions = json.load(f)
        except (json.JSONDecodeError, ValueError):
            sessions = []
    else:
        sessions = []

    # Append new session
    sessions.append(session)

    # Save back to file
    with open(SESSIONS_FILE, "w") as f:
        json.dump(sessions, f, indent=2)


# CRP (Context Relay Protocol) functions
def increment_agent_number(session: Dict[str, Any]) -> None:
    """Increment the agent number for relay handoff."""
    session["agent_number"] += 1


def add_relay_protocol(session: Dict[str, Any], protocol: Dict[str, Any]) -> None:
    """Add a relay protocol to the session's protocol list."""
    session["relay_protocols"].append(protocol)


def get_current_agent_number(session: Dict[str, Any]) -> int:
    """Get the current agent number from session."""
    return session.get("agent_number", 0)


def get_all_protocols(session: Dict[str, Any]) -> list:
    """Get all accumulated relay protocols from session."""
    return session.get("relay_protocols", [])


def get_current_agent_tokens(session: Dict[str, Any]) -> int:
    """
    Calculate tokens used by current agent only (excluding previous relays).

    Args:
        session: Session object containing metrics and relay protocols

    Returns:
        Token count for current agent since last relay (or session start)
    """
    current_total = session["metrics"]["total_tokens"]

    # If no protocols exist, current agent is agent 0 - all tokens are theirs
    if not session.get("relay_protocols"):
        return current_total

    # Get the most recent protocol (last handoff)
    last_protocol = session["relay_protocols"][-1]
    tokens_at_last_relay = last_protocol["metrics"]["snapshot_total_tokens"]

    # Current agent's tokens = total - tokens accumulated before relay
    return current_total - tokens_at_last_relay


# LLM Call Logging for debugging
def log_llm_call(
    call_type: str,
    model: str,
    messages: list,
    response_content: str,
    usage: Optional[Dict[str, Any]] = None,
    duration_seconds: Optional[float] = None
) -> None:
    """
    Log detailed LLM call information to a human-readable file.

    Args:
        call_type: Type of call (e.g., "protocol_generation", "ctf_command")
        model: Model name/identifier
        messages: List of message dicts with 'role' and 'content'
        response_content: The raw response from the LLM
        usage: Optional usage statistics dict
        duration_seconds: Optional duration of the call
    """
    ensure_state_dir()

    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    log_lines = [
        "=" * 80,
        f"[{timestamp}] {call_type.upper()} | Model: {model}",
        "=" * 80,
        "",
        ">>> MESSAGES SENT TO LLM >>>",
        ""
    ]

    # Format messages
    for msg in messages:
        role = msg.get("role", "unknown").upper()
        content = msg.get("content", "")
        log_lines.append(f"[{role}]")
        log_lines.append(content)
        log_lines.append("")

    # Add response
    log_lines.extend([
        "<<< RESPONSE FROM LLM <<<",
        "",
        response_content,
        ""
    ])

    # Add usage stats if available
    if usage or duration_seconds:
        log_lines.append("--- USAGE STATS ---")
        if usage:
            tokens_in = usage.get("prompt_tokens", 0)
            tokens_out = usage.get("completion_tokens", 0)
            cost = usage.get("cost", 0.0)
            log_lines.append(f"Tokens: {tokens_in} in / {tokens_out} out")
            if cost > 0:
                log_lines.append(f"Cost: ${cost:.6f}")
        if duration_seconds:
            log_lines.append(f"Duration: {duration_seconds:.2f}s")
        log_lines.append("")

    log_lines.append("=" * 80)
    log_lines.append("")
    log_lines.append("")

    # Append to log file
    with open(LLM_CALLS_LOG, "a", encoding="utf-8") as f:
        f.write("\n".join(log_lines))