"""
State manager for CTF Agent
Handles in-memory session state for the CTF agent.
Session data is persisted to results/ by the experiment runner.
"""

from typing import Dict, Any, Optional
from datetime import datetime


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