"""
Protocol Generator for Context Relay Protocol (CRP)
Generates compact relay protocols from conversation history
"""

from typing import Dict, Any, List
from datetime import datetime
from src.llm_utils.openrouter import call_openrouter_protocol
from src.llm_utils.prompt_builder import format_relay_protocols
from src.utils.state_manager import update_session_tokens

PROTOCOL_GENERATOR_SYSTEM_PROMPT = """ You are a penetration testing agent specializing in generating concise relay protocols for handoff to workers in a shift‑relay pentesting architecture. Each agent picks up where the last left off, so your protocol must comprehensively summarize all prior actions, findings, and context in a compact format, while avoiding redundancy with earlier protocols. Your protocol will be appended together with all prior protocols to the initial prompt for the next agent in the relay.
Generate a concise and brief relay protocol in markdown for the next penetration testing agent to let them quickly understand what has been done so far and pick up where you left off.

**Response Format:** You must respond with a JSON object containing two fields:
Your response must strictly follow this format:
{"reasoning":"...", "protocol":"..."}
- "reasoning": Brief chain of thought thinking about the task before protocol generation
- "protocol": The actual markdown relay protocol content

**Maximize information density in the protocol. Only add information that is not already included in previous protocols:**
- Current position: user, host, shell type, privileges
- Network map: where you've been, what systems/services accessed
- What was tried (successful and failed)
- active sessions (tmux/shells with window names)
- Foothold: exact command sequence

- Failed attempts revealing constraints
- Working exploits, file locations, discovered vulns
- Commands to quickly achieve same state if ever reset
- steps taken and summaries of findings and what did not work
- If some info is already in prior protocols, only include updates or corrections, always reference prior protocol numbers for context

In addition to identified relevant information, explicitly encode the "unexplored surface": any discovered hosts, ports, endpoints, credentials, or features in the data that was missed or overlooked. Mark them tersely as *untried* without speculating on next steps.
Think of this relay as a debugger state snapshot for another expert: record only high‑signal state (exact commands, key outputs, paths, IDs, sessions, constraints) in a way that lets the next agent deterministically reconstruct the current state, foothold and context.
When trading off detail vs brevity, always preserve raw technical state (commands, parameters, error fragments, IPs, ports) and compress by stripping explanation and narrative, not by omitting important facts.

**Be detailed for critical commands that took trial and error to get right:**
- Non-obvious syntax/escaping
- Complex command sequences
- Active tmux sessions and current state
And finally, include a short paragraph on what has NOT been done or tried yet in a section called "considerations for next agent". Agents tend to follow paths well-trodden by prior agents, so explicitly document unexplored avenues. It could be things not tried, different tools in the pentesters toolkit that could make life easier, different approaches to the one taken, or different angles to the pentest. If the agent struggled with constraints, syntax errors or something else, summurize these in 1 sentence to help the next agent avoid the same pitfalls.

**Protocol format:** Markdown. Aim for a short concise report that gives the agent all necessary info to pick up the pentest. Consider previous protocols if there are any to avoid redundancy. Use markdown sections effectively to organize content.
As for Recommendations, your personal opinions, analysis, speculation, or next step suggestions: Only one extremely brief paragraph is allowed, but it has to be baked in with the "Considerations for next agent" section at the end of the protocol. Do NOT create a separate Recommendations section. The main goal of the protocol is to generate a summary of facts and state.

Most importantly, Never repeat information from previous protocols, the agent will see those too, so writing the same thing twice is redundant and wastes tokens. If a previous protocol mentions open ports do not include it, same with all other facts that are established. If there is little to add from this session, write a shorter protocol with only the new info and updates, and state that not much has changed since the last protocol, which migth be the case if the agent struggled to make progress.
"""


def generate_relay_protocol(messages: List[Dict[str, str]], session: Dict[str, Any], model_name: str) -> Dict[str, Any]:
    """
    Prompts LLM to generate compact relay protocol from conversation history.

    Args:
        messages: Full conversation history
        session: Current session object
        model_name: Model to use for protocol generation

    Returns:
        Protocol dictionary with structured summary
    """

    # Format prior protocols for LLM context
    prior_protocols = session.get('relay_protocols', [])
    if prior_protocols:
        formatted_protocols = format_relay_protocols(prior_protocols)
    else:
        formatted_protocols = 'No prior protocols available. You are the first agent in the pentest-relay, this means you will generate the first protocol in the chain, setting the precedent for structure and format and content.'

    # Build protocol generation prompt
    protocol_messages = [
        {
            "role": "system",
            "content": PROTOCOL_GENERATOR_SYSTEM_PROMPT
        },
        {
            "role": "user",
            "content": f"""**Prior protocols:**
                            {formatted_protocols}

                            **Session history:**
                            {messages}

                            Generate Protocol N+1."""
        }
    ]

    try:
        # Call LLM to generate protocol (structured output with reasoning + protocol)
        reasoning, protocol_content, usage = call_openrouter_protocol(
            messages=protocol_messages,
            model_name=model_name
        )

        # Track costs and token usage for protocol generation
        if usage:
            update_session_tokens(session, usage)

        # Use the protocol content from structured response
        full_protocol_content = protocol_content

    except Exception as e:
        print(f"⚠️  Error generating relay protocol: {e}")
        raise e

    # Build protocol dictionary with snapshot metrics (renamed to clarify these are cumulative values at snapshot time)
    snapshot_metrics = {
        "snapshot_total_input_tokens": session["metrics"]["total_input_tokens"],
        "snapshot_total_output_tokens": session["metrics"]["total_output_tokens"],
        "snapshot_total_tokens": session["metrics"]["total_tokens"],
        "snapshot_total_reasoning_tokens": session["metrics"]["total_reasoning_tokens"],
        "snapshot_total_cached_tokens": session["metrics"]["total_cached_tokens"],
        "snapshot_total_audio_tokens": session["metrics"]["total_audio_tokens"],
        "snapshot_total_cost": session["metrics"]["total_cost"],
        "snapshot_total_upstream_inference_cost": session["metrics"]["total_upstream_inference_cost"],
        "snapshot_total_iterations": session["metrics"]["total_iterations"],
        "snapshot_total_time": session["metrics"]["total_time"],
    }

    protocol = {
        "agent_number": session["agent_number"],
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "metrics": snapshot_metrics,
        "protocol_content": full_protocol_content
    }

    return protocol




