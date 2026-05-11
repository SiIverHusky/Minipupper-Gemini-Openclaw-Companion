"""
Minipupper Phase 2 - Protocol Handler

Processes structured minipupper-v1 messages from OpenClaw agent.
Provides clean status/result extraction without LLM summarization
for structured messages.
"""

import json
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = "minipupper-v1"

# Minimum threshold for meaningful progress announcements
# Skip status messages that don't represent real progress
MIN_PROGRESS_DELTA = 5.0  # Only announce if progress changed by at least 5%
IGNORE_BEFORE_AGE = 120  # Ignore messages older than 120 seconds (startup filter)


def parse_protocol_message(raw_frame: dict) -> Optional[dict]:
    """Extract a structured protocol message from a Gateway frame.

    Args:
        raw_frame: Raw Gateway event dict

    Returns:
        Parsed protocol message dict, or None if not a protocol message
    """
    # session.message events
    if raw_frame.get("event") == "session.message":
        payload = raw_frame.get("payload", {})
        msg = payload.get("message", {})
        content = msg.get("content", "")
        if not content:
            return None
        try:
            d = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return None
        if isinstance(d, dict) and d.get("protocol") == PROTOCOL_VERSION:
            return d

    # Direct payload fields
    payload = raw_frame.get("payload", {})
    if isinstance(payload, dict) and payload.get("protocol") == PROTOCOL_VERSION:
        return payload

    return None


def extract_status(d: dict, min_progress_delta: float = 5.0) -> dict:
    """Extract a clean status dict from a protocol message.

    Returns: dict with keys: taskId, phase, progress, message, result,
             is_result, is_error, is_noop
    """
    msg_type = d.get("type", "")
    result = {
        "taskId": d.get("taskId", ""),
        "phase": "",
        "progress": 0.0,
        "message": "",
        "result": "",
        "is_result": False,
        "is_error": False,
        "is_noop": True,  # Default: noop=true (skip unless meaningful)
    }

    if msg_type == "status":
        result["phase"] = d.get("phase", "")
        try:
            result["progress"] = float(d.get("progress", 0.0))
        except (ValueError, TypeError):
            result["progress"] = 0.0
        result["message"] = d.get("message", "")
        # Only meaningful if there's actual content
        if result["message"] and len(result["message"]) > 3:
            result["is_noop"] = False

    elif msg_type == "result":
        result["is_result"] = True
        result["phase"] = "finished"
        result["progress"] = 100.0
        result["message"] = d.get("result", "")
        result["result"] = d.get("result", "")
        result["is_error"] = d.get("status") == "failed"
        # Result messages are always meaningful
        result["is_noop"] = False

    return result


def build_announcement_prompt(status: dict) -> str:
    """Build a prompt for the LLM to generate a user-facing status announcement.

    For structured messages, we give the LLM clean data instead of raw text.
    """
    if status.get("is_result"):
        if status.get("is_error"):
            return (
                f"The agent finished task {status['taskId'][:8]} but encountered an error. "
                f"Error: {status.get('message', 'Unknown error')}. "
                "Summarize this briefly for the user."
            )
        else:
            return (
                f"The agent completed task {status['taskId'][:8]}. "
                f"Result: {status.get('result', 'Task completed')}. "
                "Summarize this briefly for the user."
            )
    else:
        return (
            f"Task {status['taskId'][:8]} is in phase '{status['phase']}' "
            f"at {status['progress']:.0f}% progress. "
            f"Detail: {status.get('message', '')}. "
            "Summarize this briefly for the user. "
            "If progress is 0 or 100, mention it naturally."
        )


def handle_protocol_frame(frame: dict, llm, started_at: float = 0.0) -> Optional[str]:
    """Handle a protocol frame and return a TTS announcement.

    Args:
        frame: Raw Gateway frame
        llm: LLM provider instance for summarization
        started_at: App start time (epoch). Messages older than this are skipped.

    Returns:
        Announcement text to speak, or None if not a protocol frame
    """
    parsed = parse_protocol_message(frame)
    if not parsed:
        return None

    # Filter stale messages (arrived before app startup)
    msg_time = parsed.get("timestamp", 0)
    if started_at > 0 and msg_time > 0 and msg_time < started_at - 1:
        logger.debug("Skipping stale protocol message from %.1f (started at %.1f)",
                     msg_time, started_at)
        return None

    status = extract_status(parsed)

    # Skip noop messages (status updates with no meaningful content)
    if status.get("is_noop", True):
        logger.debug("Skipping noop status message for task %s: %s",
                     status["taskId"][:8], status.get("message", "")[:40])
        return None

    try:
        from src.core.llm_engine import Message
        messages = [
            Message(role="system", content=(
                "You are a concise status announcer for a robot operator. "
                "Keep responses under 2 sentences. Sound natural and helpful."
            )),
            Message(role="user", content=prompt),
        ]
        announcement = llm.generate_response(messages=messages, max_tokens=80)
        return announcement
    except Exception as e:
        logger.warning("LLM summarization failed: %s", e)
        # Fallback to raw message
        if status.get("message"):
            return status["message"]
        if status.get("result"):
            return status["result"]
        return f"Task {status.get('phase', 'in progress')}"
