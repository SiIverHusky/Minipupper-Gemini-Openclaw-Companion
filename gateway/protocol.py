"""
Minipupper Phase 2 - Agent↔App Communication Protocol

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

# ── Message Types ──────────────────────────────────────────────

# App → Agent
MSG_TASK = "task"         # New task request from Gemini
MSG_STATUS_QUERY = "status_query"  # On-demand progress check

# Agent → App
MSG_STATUS = "status"     # Periodic/task progress update
MSG_RESULT = "result"     # Final task result (completed/failed)


@dataclass
class TaskMessage:
    """A task request from the app (originating from Gemini/user)."""
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
    """Progress/status update from agent to app."""
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
    """Final result from agent to app (task completed or failed)."""
    protocol: str = PROTOCOL_VERSION
    type: str = MSG_RESULT
    taskId: str = ""
    status: str = "completed"  # completed | failed
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


# ── Task Manager ───────────────────────────────────────────────

class TaskTracker:
    """Tracks active and completed tasks.

    Provides methods for creating, updating, and querying tasks.
    Stores state as JSON for persistence across agent restarts.
    """

    def __init__(self, state_path: str = ""):
        import os
        self._tasks: dict[str, dict] = {}
        self._state_path = state_path or os.path.expanduser(
            "~/.openclaw/workspace/minipupper/tasks.json"
        )
        self._load()

    def _load(self):
        import os
        if os.path.exists(self._state_path):
            try:
                with open(self._state_path) as f:
                    self._tasks = json.load(f)
            except Exception:
                self._tasks = {}

    def _save(self):
        import os
        os.makedirs(os.path.dirname(self._state_path), exist_ok=True)
        with open(self._state_path, "w") as f:
            json.dump(self._tasks, f, indent=2)

    def create_task(self, task_msg: TaskMessage) -> str:
        task_id = task_msg.taskId or str(uuid.uuid4())
        self._tasks[task_id] = {
            "taskId": task_id,
            "action": task_msg.action,
            "params": task_msg.params,
            "userQuery": task_msg.userQuery,
            "status": "running",
            "phase": "starting",
            "progress": 0.0,
            "message": "Task received, starting...",
            "createdAt": time.time(),
            "updatedAt": time.time(),
            "result": None,
            "error": None,
        }
        self._save()
        return task_id

    def update_status(self, task_id: str, phase: str = "",
                      progress: float = 0.0, message: str = "") -> bool:
        if task_id not in self._tasks:
            return False
        task = self._tasks[task_id]
        if phase:
            task["phase"] = phase
        task["progress"] = max(0.0, min(100.0, progress))
        if message:
            task["message"] = message
        task["updatedAt"] = time.time()
        self._save()
        return True

    def complete_task(self, task_id: str, result: str,
                      error: Optional[str] = None) -> bool:
        if task_id not in self._tasks:
            return False
        self._tasks[task_id].update({
            "status": "failed" if error else "completed",
            "phase": "finished",
            "progress": 100.0,
            "message": error or "Task completed successfully.",
            "result": result,
            "error": error,
            "updatedAt": time.time(),
        })
        self._save()
        return True

    def get_task(self, task_id: str) -> Optional[dict]:
        return self._tasks.get(task_id)

    def get_active_tasks(self) -> list[dict]:
        return [t for t in self._tasks.values()
                if t.get("status") == "running"]

    def get_all_tasks(self) -> list[dict]:
        return list(self._tasks.values())

    def build_status_message(self, task_id: str) -> Optional[StatusMessage]:
        task = self.get_task(task_id)
        if not task:
            return None
        return StatusMessage(
            taskId=task_id,
            phase=task.get("phase", ""),
            progress=task.get("progress", 0.0),
            message=task.get("message", ""),
        )


# ── Singleton ──────────────────────────────────────────────────

_tracker: Optional[TaskTracker] = None


def get_tracker() -> TaskTracker:
    global _tracker
    if _tracker is None:
        _tracker = TaskTracker()
    return _tracker


# ── Protocol Helpers ───────────────────────────────────────────

def parse_message(raw: str) -> Optional[dict]:
    """Parse a raw message string into a protocol message dict.

    Returns None if it doesn't match the protocol.
    """
    try:
        d = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None

    if not isinstance(d, dict):
        return None
    if d.get("protocol") != PROTOCOL_VERSION:
        return None
    return d


def is_valid_message(d: dict) -> bool:
    """Check if a dict is a valid protocol message."""
    return d.get("protocol") == PROTOCOL_VERSION and d.get("type") in (
        MSG_TASK, MSG_STATUS_QUERY, MSG_STATUS, MSG_RESULT
    )


def new_task_id() -> str:
    return str(uuid.uuid4())