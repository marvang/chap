"""
Discord Integration - Limit Warning Messages
Handles limit threshold notifications (cost, iteration).
"""

import discord
from typing import Dict, Any
from .core import _safe_send, _create_embed


def send_cost_limit_warning_message(channel_id, data: Dict[str, Any]) -> bool:
    """
    Send cost limit warning notification.

    Args:
        channel_id: Discord channel ID
        data: Dict with keys:
            - challenge: Challenge name
            - current_cost: Current cost (float)
            - max_cost: Maximum allowed cost (float)
            - experiment_id: Experiment ID (optional)

    Returns:
        True if successful, False otherwise

    Example:
        >>> send_cost_limit_warning_message(
        ...     channel_id="123456789",
        ...     data={
        ...         "challenge": "vm0",
        ...         "current_cost": 5.25,
        ...         "max_cost": 5.00,
        ...         "experiment_id": "20250527_143022"
        ...     }
        ... )
    """
    if not channel_id:
        return False

    challenge = data.get("challenge", "Unknown")
    current_cost = data.get("current_cost", 0.0)
    max_cost = data.get("max_cost", 0.0)
    experiment_id = data.get("experiment_id", "")

    # Calculate percentage
    percentage = (current_cost / max_cost * 100) if max_cost > 0 else 0

    fields = [
        {"name": "Challenge", "value": challenge, "inline": True},
        {"name": "Current Cost", "value": f"${current_cost:.2f}", "inline": True},
        {"name": "Max Cost", "value": f"${max_cost:.2f}", "inline": True},
        {"name": "Percentage", "value": f"{percentage:.1f}%", "inline": True}
    ]

    if experiment_id:
        fields.insert(0, {"name": "Experiment", "value": experiment_id, "inline": True})

    embed = _create_embed(
        title="💰 Cost Limit Reached",
        description="⚠️ Challenge has reached the cost threshold",
        color=discord.Color.orange(),
        fields=fields
    )

    return _safe_send(channel_id, embed=embed)


def send_iteration_limit_warning_message(channel_id, data: Dict[str, Any]) -> bool:
    """
    Send iteration limit warning notification.

    Args:
        channel_id: Discord channel ID
        data: Dict with keys:
            - challenge: Challenge name
            - iterations: Current iteration count (int)
            - max_iterations: Maximum allowed iterations (int)
            - experiment_id: Experiment ID (optional)

    Returns:
        True if successful, False otherwise

    Example:
        >>> send_iteration_limit_warning_message(
        ...     channel_id="123456789",
        ...     data={
        ...         "challenge": "vm0",
        ...         "iterations": 42,
        ...         "max_iterations": 40,
        ...         "experiment_id": "20250527_143022"
        ...     }
        ... )
    """
    if not channel_id:
        return False

    challenge = data.get("challenge", "Unknown")
    iterations = data.get("iterations", 0)
    max_iterations = data.get("max_iterations", 0)
    experiment_id = data.get("experiment_id", "")

    # Calculate percentage
    percentage = (iterations / max_iterations * 100) if max_iterations > 0 else 0

    fields = [
        {"name": "Challenge", "value": challenge, "inline": True},
        {"name": "Current Iterations", "value": str(iterations), "inline": True},
        {"name": "Max Iterations", "value": str(max_iterations), "inline": True},
        {"name": "Percentage", "value": f"{percentage:.1f}%", "inline": True}
    ]

    if experiment_id:
        fields.insert(0, {"name": "Experiment", "value": experiment_id, "inline": True})

    embed = _create_embed(
        title="🔄 Iteration Limit Reached",
        description="⚠️ Challenge has reached the iteration threshold",
        color=discord.Color.orange(),
        fields=fields
    )

    return _safe_send(channel_id, embed=embed)
