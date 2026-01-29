"""
Discord Integration for CTF Agent Experiments
Provides webhook notifications for experiment tracking and monitoring.
"""

# Core functionality
from .core import (
    create_experiment_channel,
    create_experiment_category,
    create_challenge_channel
)

# Experiment-level messages
from .experiment_messages import (
    send_experiment_start_message,
    send_experiment_complete_message,
    send_experiment_interrupted_message,
    send_experiment_error_message
)

# Challenge-level messages
from .challenge_messages import (
    send_challenge_start_message,
    send_challenge_complete_message,
    send_challenge_error_message
)

# Limit warnings
from .limit_messages import (
    send_cost_limit_warning_message,
    send_iteration_limit_warning_message
)

# Error alerts
from .error_messages import (
    send_error_alert_message,
    send_llm_error_message,
    send_command_timeout_message,
    send_empty_command_stop_message,
    send_docker_connection_error_message
)


# Relay notifications
from .relay_messages import (
    send_auto_relay_message,
    send_manual_relay_message
)

__all__ = [
    # Core
    "create_experiment_channel",
    "create_experiment_category",
    "create_challenge_channel",

    # Experiment messages
    "send_experiment_start_message",
    "send_experiment_complete_message",
    "send_experiment_interrupted_message",
    "send_experiment_error_message",

    # Challenge messages
    "send_challenge_start_message",
    "send_challenge_complete_message",
    "send_challenge_error_message",

    # Limit warnings
    "send_cost_limit_warning_message",
    "send_iteration_limit_warning_message",

    # Error alerts
    "send_error_alert_message",
    "send_llm_error_message",
    "send_command_timeout_message",
    "send_empty_command_stop_message",
    "send_docker_connection_error_message",

    # Flag capture
    # Relay notifications
    "send_auto_relay_message",
    "send_manual_relay_message",
]
