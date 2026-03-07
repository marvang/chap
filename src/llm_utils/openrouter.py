import os
import json
import re
import socket
import time
from http.client import IncompleteRead
from typing import Tuple, Dict, Any
from urllib import request
from urllib.error import HTTPError, URLError
from dotenv import load_dotenv
from src.llm_utils.response_schema import get_ctf_response_schema



def call_openrouter_with_history(messages: list, model_name: str) -> Tuple[str, str, Dict[str, Any], str]:
    """
    Call OpenRouter API with full message history for context-aware responses

    Args:
        messages: List of message dicts with 'role' and 'content' keys
        model_name: OpenRouter model identifier

    Returns:
        Tuple of (reasoning, shell_command, usage, extended_reasoning) parsed from LLM response
    """
    load_dotenv()

    api_key_env = "OPENROUTER_API_KEY"
    api_key = os.getenv(api_key_env)
    if not api_key:
        raise RuntimeError(f"{api_key_env} not found in environment variables")

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model_name,
        "messages": messages,
        # "provider": {
        #     "require_parameters": True,
        #     "only": ["openai", "anthropic"],
        # },
        # "quantizations": ["fp8"],
        "usage": {"include": True},
        "response_format": get_ctf_response_schema(),
        #"temperature": 1, # Not available for openai models
        #"seed": 1, # not available for anthropic models
    }

    req = request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    
    # Retry logic: 3 attempts with 2-second delay
    max_attempts = 3
    last_error_details = None
    
    for attempt in range(1, max_attempts + 1):
        try:
            with request.urlopen(req, timeout=600) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            break  # Success, exit retry loop
        except HTTPError as e:
            # Try to read and parse the error response body
            error_details = {
                "http_code": e.code,
                "http_reason": e.reason,
                "attempt": attempt,
            }
            try:
                error_body = e.read().decode("utf-8")
                error_json = json.loads(error_body)
                if "error" in error_json:
                    error_details["message"] = error_json["error"].get("message")
                    error_details["metadata"] = error_json["error"].get("metadata")
                else:
                    error_details["raw_response"] = error_body
            except Exception:
                error_details["raw_response"] = str(e)
            
            last_error_details = error_details
            
            if attempt < max_attempts:
                print(f"⚠️  OpenRouter HTTP error (attempt {attempt}/{max_attempts}): {e.code} {e.reason}. Retrying in 2s...")
                time.sleep(2)
                # Recreate request since body stream was consumed
                req = request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
            else:
                # Final attempt failed, raise with detailed error
                raise RuntimeError(f"OpenRouter API error: {json.dumps(last_error_details)}")
        except URLError as e:
            last_error_details = {
                "error_type": "URLError",
                "reason": str(e.reason),
                "attempt": attempt,
            }
            
            if attempt < max_attempts:
                print(f"⚠️  OpenRouter URL error (attempt {attempt}/{max_attempts}): {e.reason}. Retrying in 2s...")
                time.sleep(2)
                req = request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
            else:
                raise RuntimeError(f"OpenRouter API error: {json.dumps(last_error_details)}")
        except IncompleteRead as e:
            last_error_details = {
                "error_type": "IncompleteRead",
                "bytes_read": str(e.partial) if hasattr(e, 'partial') else str(e),
                "attempt": attempt,
            }
            
            if attempt < max_attempts:
                print(f"⚠️  OpenRouter incomplete read (attempt {attempt}/{max_attempts}): {e}. Retrying in 2s...")
                time.sleep(2)
                req = request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
            else:
                raise RuntimeError(f"OpenRouter API error: {json.dumps(last_error_details)}")
        except socket.timeout as e:
            last_error_details = {
                "error_type": "Timeout",
                "message": str(e),
                "attempt": attempt,
            }
            
            if attempt < max_attempts:
                print(f"⚠️  OpenRouter timeout (attempt {attempt}/{max_attempts}): {e}. Retrying in 2s...")
                time.sleep(2)
                req = request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
            else:
                raise RuntimeError(f"OpenRouter API error: {json.dumps(last_error_details)}")

    try:
        content = data["choices"][0]["message"]["content"]
        extended_reasoning = data["choices"][0]["message"].get("reasoning", "")
    except Exception:
        content = json.dumps(data)
        extended_reasoning = ""

    # Parse JSON response - try multiple strategies
    reasoning = ""
    shell_command = ""

    # Strategy 1: Try to parse as pure JSON
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            reasoning = parsed.get("reasoning", "")
            shell_command = parsed.get("shell_command", "")

            # If we got both fields, we're done
            if reasoning and shell_command:
                usage = data.get("usage", {})
                return reasoning, shell_command, usage, extended_reasoning
    except json.JSONDecodeError:
        pass

    # Strategy 2: Try to extract JSON from markdown code blocks
    json_pattern = r'```(?:json)?\s*(\{.*?\})\s*```'
    matches = re.findall(json_pattern, content, re.DOTALL)
    for match in matches:
        try:
            parsed = json.loads(match)
            if isinstance(parsed, dict):
                reasoning = parsed.get("reasoning", "")
                shell_command = parsed.get("shell_command", "")

                if reasoning and shell_command:
                    usage = data.get("usage", {})
                    return reasoning, shell_command, usage, extended_reasoning
        except json.JSONDecodeError:
            continue

    # Strategy 3: Try to find JSON object in the text
    json_obj_pattern = r'\{[^{}]*"reasoning"[^{}]*"shell_command"[^{}]*\}'
    matches = re.findall(json_obj_pattern, content, re.DOTALL)
    for match in matches:
        try:
            parsed = json.loads(match)
            if isinstance(parsed, dict):
                reasoning = parsed.get("reasoning", "")
                shell_command = parsed.get("shell_command", "")

                if reasoning and shell_command:
                    usage = data.get("usage", {})
                    return reasoning, shell_command, usage, extended_reasoning
        except json.JSONDecodeError:
            continue

    # Fallback: If all parsing failed, return content as reasoning
    if not reasoning:
        reasoning = content

    # Extract usage information
    usage = data.get("usage", {})

    return reasoning, shell_command, usage, extended_reasoning

# For Protocol Generation - structured output with reasoning + protocol
def call_openrouter_protocol(messages: list, model_name: str) -> Tuple[str, str, Dict[str, Any]]:
    """
    Call OpenRouter API for protocol generation with structured output.

    Args:
        messages: List of message dicts with 'role' and 'content' keys
        model_name: OpenRouter model identifier

    Returns:
        Tuple of (reasoning, protocol, usage) parsed from LLM response
    """
    from src.llm_utils.response_schema import get_protocol_response_schema
    load_dotenv()

    # Start timing
    start_time = time.time()
    api_key_env = "OPENROUTER_API_KEY"
    api_key = os.getenv(api_key_env)
    if not api_key:
        raise RuntimeError(f"{api_key_env} not found in environment variables")

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model_name,
        "messages": messages,
        # "provider": {
        #     "require_parameters": True,
        # "only": ["openai"],
        # },
        "usage": {"include": True},
        "response_format": get_protocol_response_schema(),
    }

    req = request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    
    # Retry logic: 3 attempts with 2-second delay
    max_attempts = 3
    last_error_details = None
    
    for attempt in range(1, max_attempts + 1):
        try:
            with request.urlopen(req, timeout=600) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            break  # Success, exit retry loop
        except HTTPError as e:
            error_details = {
                "http_code": e.code,
                "http_reason": e.reason,
                "attempt": attempt,
            }
            try:
                error_body = e.read().decode("utf-8")
                error_json = json.loads(error_body)
                if "error" in error_json:
                    error_details["message"] = error_json["error"].get("message")
                    error_details["metadata"] = error_json["error"].get("metadata")
                else:
                    error_details["raw_response"] = error_body
            except Exception:
                error_details["raw_response"] = str(e)
            
            last_error_details = error_details
            
            if attempt < max_attempts:
                print(f"⚠️  OpenRouter HTTP error (attempt {attempt}/{max_attempts}): {e.code} {e.reason}. Retrying in 2s...")
                time.sleep(2)
                req = request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
            else:
                raise RuntimeError(f"OpenRouter API error: {json.dumps(last_error_details)}")
        except URLError as e:
            last_error_details = {
                "error_type": "URLError",
                "reason": str(e.reason),
                "attempt": attempt,
            }
            
            if attempt < max_attempts:
                print(f"⚠️  OpenRouter URL error (attempt {attempt}/{max_attempts}): {e.reason}. Retrying in 2s...")
                time.sleep(2)
                req = request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
            else:
                raise RuntimeError(f"OpenRouter API error: {json.dumps(last_error_details)}")
        except IncompleteRead as e:
            last_error_details = {
                "error_type": "IncompleteRead",
                "bytes_read": str(e.partial) if hasattr(e, 'partial') else str(e),
                "attempt": attempt,
            }
            
            if attempt < max_attempts:
                print(f"⚠️  OpenRouter incomplete read (attempt {attempt}/{max_attempts}): {e}. Retrying in 2s...")
                time.sleep(2)
                req = request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
            else:
                raise RuntimeError(f"OpenRouter API error: {json.dumps(last_error_details)}")
        except socket.timeout as e:
            last_error_details = {
                "error_type": "Timeout",
                "message": str(e),
                "attempt": attempt,
            }
            
            if attempt < max_attempts:
                print(f"⚠️  OpenRouter timeout (attempt {attempt}/{max_attempts}): {e}. Retrying in 2s...")
                time.sleep(2)
                req = request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
            else:
                raise RuntimeError(f"OpenRouter API error: {json.dumps(last_error_details)}")

    try:
        content = data["choices"][0]["message"]["content"]
    except Exception:
        content = json.dumps(data)

    # Parse JSON response
    reasoning = ""
    protocol = ""
    
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            reasoning = parsed.get("reasoning", "")
            protocol = parsed.get("protocol", "")
    except json.JSONDecodeError:
        # Fallback: use content as protocol if parsing fails
        protocol = content

    # Extract usage information
    usage = data.get("usage", {})

    return reasoning, protocol, usage

