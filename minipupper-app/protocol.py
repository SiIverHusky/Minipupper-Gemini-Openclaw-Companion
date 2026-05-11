"""
Minipupper Phase 2 - Agent<->App Communication Protocol

Structured JSON-over-sessions protocol for reliable task offloading,
status reporting, and result delivery between the OpenClaw agent
and the Minipupper Operator app.

Protocol version: minipupper-v1
Session: minipupper-app (dedicated)
"""

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional, Any

PROTOCOL_VERSION = "minipupper-v1"
APP_SESSION_KEY = "minipupper-app"

# -- Message Types --
MSG_TASK = "task"           # App -> Agent: new task request from Gemini
MSG_STATUS_QUERY = "status_query"  # App -> Agent: on-demand progress check
MSG_STATUS = "status"       # Agent -> App: periodic/task progress update
MSG_RESULT = "result"       # Agent -> App: final task result


@dataclass
class TaskMessage:
    protocol: str = PROTOCOL_VERSION
    type: str = MSG_TASK
    taskId: str = ""
    action: str = ""
    params: dict = field(default_factory=dict)
    userQuery: str = ""
    timestamp: float = 0.0

    @classmethod
    def from_dict(cls, d: dict) -> "TaskMessage":
        return cls(
            protocol=d.get("protocol", PROTOCOL_VERSION),
            type=d.get("type", MSG_TASK),
            taskId=d.get("taskId", ""),
            action=d.get("action", ""),
            params=d.get("params", {}),
            userQuery=d.get("userQuery", ""),
            timestamp=d.get("timestamp", time.time()),
        )

    def to_dict(self) -> dict:
        return {
            "protocol": self.protocol,
            "type": self.type,
            "taskId": self.taskId,
            "action": self.action,
            "params": self.params,
            "userQuery": self.userQuery,
            "timestamp": self.timestamp or time.time(),
        }


@dataclass
class StatusMessage:
    protocol: str = PROTOCOL_VERSION
    type: str = MSG_STATUS
    taskId: str = ""
    phase: str = ""
    progress: float = 0.0
    message: str = ""
    timestamp: float = 0.0

    @classmethod
    def from_dict(cls, d: dict) -> "StatusMessage":
        return cls(
            protocol=d.get("protocol", PROTOCOL_VERSION),
            type=d.get("type", MSG_STATUS),
            taskId=d.get("taskId", ""),
            phase=d.get("phase", ""),
            progress=d.get("progress", 0.0),
            message=d.get("message", ""),
            timestamp=d.get("timestamp", time.time()),
        )

    def to_dict(self) -> dict:
        return {
            "protocol": self.protocol,
            "type": self.type,
            "taskId": self.taskId,
            "phase": self.phase,
            "progress": self.progress,
            "message": self.message,
            "timestamp": self.timestamp or time.time(),
        }


@dataclass
class ResultMessage:
    protocol: str = PROTOCOL_VERSION
    type: str = MSG_RESULT
    taskId: str = ""
    status: str = "completed"
    result: str = ""
    error: Optional[str] = None
    timestamp: float = 0.0

    @classmethod
    def from_dict(cls, d: dict) -> "ResultMessage":
        return cls(
            protocol=d.get("protocol", PROTOCOL_VERSION),
            type=d.get("type", MSG_RESULT),
            taskId=d.get("taskId", ""),
            status=d.get("status", "completed"),
            result=d.get("result", ""),
            error=d.get("error"),
            timestamp=d.get("timestamp", time.time()),
        )

    def to_dict(self) -> dict:
        return {
            "protocol": self.protocol,
            "type": self.type,
            "taskId": self.taskId,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "timestamp": self.timestamp or time.time(),
        }


def parse_message(raw: str) -> Optional[dict]:
    """Parse a raw message string into a protocol message dict."""
    try:
        d = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(d, dict):
        return None
    if d.get("protocol") != PROTOCOL_VERSION:
        return None
    return d


def new_task_id() -> str:
    return str(uuid.uuid4())
