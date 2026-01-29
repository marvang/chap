"""Prompt building utilities for LLM initialization"""
from typing import List, Dict, Optional
from src.llm_utils import prompts


def build_initial_messages(
    use_vpn: bool,
    target_info: str,
    use_chap: bool,
    custom_instructions: str = "",
    agent_ips: Optional[dict] = None,
    use_amd64_prompt: bool = False
) -> List[Dict[str, str]]:
    """
    Build initial message list for LLM conversation

    Args:
        use_vpn: Whether HackTheBox VPN is being used
        target_info: Target IP address or "Local container"
        use_chap: Whether CHAP protocol should be used
        custom_instructions: Optional custom user instructions
        agent_ips: Dict with agent IP addresses (eth0, tun0 if VPN)

    Returns:
        List of message dictionaries with 'role' and 'content' keys
    """
    # Select appropriate system prompt based on architecture
    if use_amd64_prompt:
        base_prompt = prompts.AMD_64_CTF_AGENT_SYSTEM_PROMPT
    else:
        base_prompt = prompts.CTF_AGENT_SYSTEM_PROMPT
    
    # Set environment context
    if use_vpn:
        system_prompt = base_prompt
        environment_context = f"Environment: HackTheBox: VPN Connected. The target ip address is: {target_info}"
    else:
        system_prompt = base_prompt
        environment_context = f"Environment: Local CTF in docker container mode. The target ip address is: {target_info}"

    # Add agent IP addresses if available
    if agent_ips:
        if 'eth0' in agent_ips:
            environment_context += f"\nAgent Docker IP (eth0): {agent_ips['eth0']}"
        if 'tun0' in agent_ips:
            environment_context += f"\nAgent VPN IP (tun0): {agent_ips['tun0']}"

    environment_context += " "

    if not use_chap:
        # Build initial user prompt with optional custom instructions
        if custom_instructions:
            initial_user_prompt = f"{environment_context}\n\n{prompts.MAIN_INIT_PROMPT}\n\nADDITIONAL CUSTOM INSTRUCTIONS FROM THE TEAM: {custom_instructions}"
        else:
            initial_user_prompt = f"{environment_context}\n\n{prompts.MAIN_INIT_PROMPT}\n\n NO ADDITIONAL CUSTOM INSTRUCTIONS FROM THE TEAM."
    
    else:
        # Build initial user prompt with optional custom instructions
        if custom_instructions:
            initial_user_prompt = f"{environment_context}\n\n{prompts.MAIN_INIT_RELAY_PROMPT}\n\nADDITIONAL CUSTOM INSTRUCTIONS FROM THE TEAM: {custom_instructions}"
        else:
            initial_user_prompt = f"{environment_context}\n\n{prompts.MAIN_INIT_RELAY_PROMPT}\n\n NO ADDITIONAL CUSTOM INSTRUCTIONS FROM THE TEAM."


    if use_chap:
        system_prompt += "\n" + prompts.CHAP


    # print the final assembled system and user prompt for debugging
    print("=== Assembled Initial System Prompt ===\n")
    print(system_prompt)
    print("\n=== Assembled Initial User Prompt ===\n")
    print(initial_user_prompt)
    print("")

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": initial_user_prompt}
    ]


def build_relay_messages(
    session: Dict,
    use_vpn: bool,
    target_info: str,
    custom_instructions: str = "",
    agent_ips: Optional[dict] = None,
    use_amd64_prompt: bool = False
) -> List[Dict[str, str]]:
    """
    Build fresh message history with accumulated relay protocols injected.

    Args:
        session: Session object containing relay protocols
        use_vpn: Whether HackTheBox VPN is being used
        target_info: Target IP address
        custom_instructions: Optional custom user instructions
        agent_ips: Dict with agent IP addresses (eth0, tun0 if VPN)

    Returns:
        Fresh message list with protocols injected into initial user message
    """
    # Start with appropriate system prompt based on architecture
    if use_amd64_prompt:
        system_prompt = prompts.AMD_64_CTF_AGENT_SYSTEM_PROMPT + "\n" + prompts.CHAP
    else:
        system_prompt = prompts.CTF_AGENT_SYSTEM_PROMPT + "\n" + prompts.CHAP

    # Build structured user message
    user_content = "=== RELAY MISSION ===\n"
    user_content += "You are continuing a CTF penetration test. Build upon the work of previous agents and then activate the next relay.\n"
    user_content += "Review their protocols below and continue from where they left off.\n\n"

    # Add environment section
    user_content += "=== ENVIRONMENT ===\n"
    if use_vpn:
        user_content += f"Type: HackTheBox VPN\nTarget IP: {target_info}\n"
    else:
        user_content += f"Type: Local CTF docker container\nTarget IP: {target_info}\n"

    # Add agent IP addresses if available
    if agent_ips:
        if 'eth0' in agent_ips:
            user_content += f"Agent Docker IP (eth0): {agent_ips['eth0']}\n"
        if 'tun0' in agent_ips:
            user_content += f"Agent VPN IP (tun0): {agent_ips['tun0']}\n"

    user_content += "Workspace: /ctf-workspace\n\n"

    # Inject all accumulated protocols if any exist
    if session.get("relay_protocols"):
        user_content += format_relay_protocols(session["relay_protocols"]) + "\n\n"

    # Add instructions section
    user_content += "=== INSTRUCTIONS ===\n"
    user_content += prompts.RELAY_PROMPT_AFTER_FIRST_RELAY

    # Add custom instructions if provided
    if custom_instructions:
        user_content += f"\n\nCustom Instructions: {custom_instructions}"

    # print the final assembled system and user prompt for debugging
    print("=== Assembled Relay System Prompt ===\n")
    print(system_prompt)
    print("\n=== Assembled Relay User Prompt ===\n")
    print(user_content)
    print("")

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]


def format_relay_protocols(protocols: List[Dict]) -> str:
    """
    Format accumulated protocols for injection into user message.

    Args:
        protocols: List of relay protocol dictionaries

    Returns:
        Formatted string with all protocols
    """
    formatted = "=== RELAY PROTOCOLS ===\n\n"

    for i, protocol in enumerate(protocols):
        protocol_num = protocol['agent_number'] + 1  # 1-indexed for readability
        formatted += f"=== PROTOCOL {protocol_num} - From PENTEST AGENT SHIFT {protocol_num} ===\n\n"
        formatted += protocol['protocol_content'] + "\n\n"
        if i < len(protocols) - 1:  # Add separator between protocols
            formatted += "---\n\n"

    formatted += f"Current Agent: You are Agent {len(protocols) + 1}.\n"

    return formatted
