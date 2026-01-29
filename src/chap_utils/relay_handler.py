"""
Relay Handler for Context Relay Protocol (CRP)
Orchestrates the handoff process between agent instances
"""

from typing import Dict, Any, List, Optional
from src.chap_utils.protocol_generator import generate_relay_protocol
from src.utils.state_manager import (
    add_relay_protocol,
    increment_agent_number,
    get_current_agent_number,
    get_current_agent_tokens
)
from src.llm_utils.prompt_builder import build_relay_messages


def trigger_relay_handoff(
    session: Dict[str, Any],
    messages: List[Dict[str, str]],
    model_name: str,
    use_vpn: bool,
    target_info: str,
    custom_instructions: str,
    current_iteration: int,
    agent_ips: Optional[dict] = None,
    use_amd64_prompt: bool = False
) -> List[Dict[str, str]]:
    """
    Executes relay handoff:
    1. Generate protocol from current history
    2. Save protocol to session
    3. Build fresh initial messages for new agent with all protocols injected
    4. Return new messages list

    Args:
        session: Current session object
        messages: Current conversation history
        model_name: Model being used
        use_vpn: Whether VPN is being used
        target_info: Target IP or description
        custom_instructions: User's custom instructions
        current_iteration: Current iteration count to accumulate
        agent_ips: Dict with agent IP addresses (eth0, tun0 if VPN)

    Returns:
        New messages list with protocols injected
    """

    # Note: iteration accumulation handled incrementally in main loop in main_experiment_agent.py
    # (session['metrics']['total_iterations'] is updated each iteration)

    # Calculate agent-specific token usage
    agent_tokens = get_current_agent_tokens(session)

    print(f"\n🔄 Initiating relay handoff...")
    print(f"📊 Current agent: Agent {session['agent_number']}")
    print(f"💰 Agent token usage: {agent_tokens:,} tokens")
    print(f"💰 Total session tokens: {session['metrics']['total_tokens']:,} tokens")
    print(f"🔄 Total iterations: {session['metrics']['total_iterations']}")
    print(f"🕒 Total time: {session['metrics']['total_time']:.2f} seconds")
    print(f"💵 Cost: ${session['metrics']['total_cost']:.4f}")

    # 1. Generate protocol from current history
    print(f"\n📝 Generating relay protocol...")
    try:
        protocol = generate_relay_protocol(messages, session, model_name)
        print(f"✅ Protocol generated successfully")
        print(f"📄 Protocol content:\n{protocol['protocol_content']}\n")
    except Exception as e:
        print(f"❌ Error generating protocol: {e}")
        # throw error and end session
        raise e

    # 2. Save protocol to session
    add_relay_protocol(session, protocol)

    # 3. Increment agent number
    increment_agent_number(session)
    new_agent_number = get_current_agent_number(session)

    # 4. Build fresh messages with protocols injected
    new_messages = build_relay_messages(
        session=session,
        use_vpn=use_vpn,
        target_info=target_info,
        custom_instructions=custom_instructions,
        agent_ips=agent_ips,
        use_amd64_prompt=use_amd64_prompt
    )

    print(f"\n✨ Relay handoff complete!")
    print(f"🤖 Now operating as Agent {new_agent_number}")
    print(f"📚 Carrying forward {len(session['relay_protocols'])} protocol(s)")
    print("="*60)

    return new_messages
