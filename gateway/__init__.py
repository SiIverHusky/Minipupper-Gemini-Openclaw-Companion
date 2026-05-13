"""
Minipupper App — Communication Channel Package

Connects the Minipupper voice/speech app to the OpenClaw agent,
providing structured task handling, robot control, and status reporting.

Protocol: minipupper-v1 (see ./protocol.py)
Session:   minipupper-app
"""

from .protocol import (
    TaskMessage,
    StatusMessage,
    ResultMessage,
    TaskTracker,
    get_tracker,
    parse_message,
    is_valid_message,
    new_task_id,
    PROTOCOL_VERSION,
    APP_SESSION_KEY,
    MSG_TASK,
    MSG_STATUS_QUERY,
    MSG_STATUS,
    MSG_RESULT,
)
from .task_handler import (
    handle_task_message,
    handle_status_query,
    send_status,
    send_result,
    router,
)

__all__ = [
    # Protocol types
    "TaskMessage",
    "StatusMessage",
    "ResultMessage",
    "TaskTracker",
    "get_tracker",
    "parse_message",
    "is_valid_message",
    "new_task_id",
    "PROTOCOL_VERSION",
    "APP_SESSION_KEY",
    "MSG_TASK",
    "MSG_STATUS_QUERY",
    "MSG_STATUS",
    "MSG_RESULT",
    # Handler functions
    "handle_task_message",
    "handle_status_query",
    "send_status",
    "send_result",
    "router",
]
