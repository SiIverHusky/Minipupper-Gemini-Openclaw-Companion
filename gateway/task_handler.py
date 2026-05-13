"""
Minipupper App — Structured Task Handler

Bridges the minipupper-app protocol (TaskMessage objects received over the
minipupper-app Gateway session) with the Minipupper robot control stack.
Flow:                                                                                            1. App sends TaskMessage via sessions.send to the "minipupper-app" session
  2. Main agent (or heartbeat) calls handle_task_message() with the raw dict                     3. Handler parses, creates a task record, routes to the right action
  4. During execution, calls send_status() to push progress updates back
  5. On completion, calls send_result() with the final output

Each handler function receives:
  - task_id: str          — unique task identifier
  - params: dict          — action-specific parameters
  - send_status_fn        — callable(phase, progress, message) for progress

Usage from the agent (e.g., during a heartbeat or session message handler):

    from minipupper import handle_task_message, send_status, send_result

    # When a messages arrives on the minipupper-app session:
    result = await handle_task_message(raw_message_dict)
    # result is a dict with {"ok": bool, "text": str, ...}
"""

import json
import time
import traceback
from typing import Any, Callable, Optional

from .protocol import (
    TaskMessage,
    StatusMessage,
    ResultMessage,
    TaskTracker,
    get_tracker,
    parse_message,
    is_valid_message,
    new_task_id,
    MSG_TASK,
    MSG_STATUS_QUERY,
)

# ── Type aliases ───────────────────────────────────────────────

# A callable that the agent implements to send a message to the minipupper-app session.
# The agent is responsible for calling sessions.send(key="minipupper-app", message=...).
SessionSendFn = Callable[[dict], Any]

# A callable that the handler can use to exec commands on the robot node.
# Signature: exec(command: str, host="node", node="minipupper-deepseek") -> ExecResult
ExecFn = Callable[..., Any]


# ── Action Router ──────────────────────────────────────────────

class ActionRouter:
    """Maps protocol actions to handler functions.

    Each handler signature: handle(task_id, params, send_status) -> dict
    where dict has at least {"ok": bool, "text": str}.
    """

    def __init__(self):
        self._handlers: dict[str, Callable] = {}

    def register(self, action: str):
        """Decorator to register an action handler."""
        def decorator(fn):
            self._handlers[action] = fn
            return fn
        return decorator

    def get(self, action: str) -> Optional[Callable]:
        return self._handlers.get(action)

    def list_actions(self) -> list[str]:
        return list(self._handlers.keys())

    def handles(self, action: str) -> bool:
        return action in self._handlers


# Singleton router
router = ActionRouter()


# ── Robot Action Handlers ──────────────────────────────────────
# These generate exec commands to run on the minipupper-deepseek node.

_ROBOT_SCRIPT = "python3 /home/ubuntu/minipupper-app/robot/robot_control.py"


def _robot_cmd(action: str, duration: Optional[float] = None, angle: Optional[float] = None) -> str:
    """Build a robot control exec command string.

    The FPC-based robot_control.py uses --duration and --angle flags.
    Positional form: robot_control.py {action} {value}
    where value is duration for movements, angle for rotation.
    """
    cmd = f"{_ROBOT_SCRIPT} {action}"
    if duration is not None:
        cmd += f" {duration}"
    elif angle is not None:
        cmd += f" {angle}"
    return cmd


@router.register("robot.init")
def _handle_init(task_id: str, params: dict,
                 send_status: Callable) -> dict:
    duration = params.get("duration", None)
    send_status("executing", 30.0, "Activating robot, raising body...")
    return {
        "ok": True,
        "text": "Robot activated and body raised.",
        "exec_command": _robot_cmd("init", duration),
    }


@router.register("robot.deactivate")
def _handle_deactivate(task_id: str, params: dict,
                        send_status: Callable) -> dict:
    send_status("executing", 50.0, "Deactivating robot...")
    return {
        "ok": True,
        "text": "Robot deactivated.",
        "exec_command": _robot_cmd("deactivate"),
    }


@router.register("robot.reset")
def _handle_reset(task_id: str, params: dict,
                  send_status: Callable) -> dict:
    send_status("executing", 30.0, "Resetting robot position...")
    return {
        "ok": True,
        "text": "Robot reset sequence initiated.",
        "exec_command": _robot_cmd("reset"),
    }


@router.register("robot.trot")
def _handle_trot(task_id: str, params: dict,
                 send_status: Callable) -> dict:
    send_status("executing", 30.0, "Toggling trot gait...")
    return {
        "ok": True,
        "text": "Trot gait toggled.",
        "exec_command": _robot_cmd("trot"),
    }


@router.register("robot.stop")
def _handle_stop(task_id: str, params: dict,
                 send_status: Callable) -> dict:
    send_status("executing", 50.0, "Stopping all movement...")
    return {
        "ok": True,
        "text": "All robot movement stopped.",
        "exec_command": _robot_cmd("stop"),
    }


# Movement commands with configurable duration
_MOVEMENT_HANDLERS = {
    "robot.move_forward":  "forward",
    "robot.move_backward": "backward",
    "robot.strafe_right":  "right",
    "robot.strafe_left":   "left",
    "robot.rotate_cw":     "cw",
    "robot.rotate_ccw":    "ccw",
    "robot.look_up":       "look-up",
    "robot.look_down":     "look-down",
    "robot.raise_body":    "raise-body",
    "robot.lower_body":    "lower-body",

}


def _make_movement_handler(subcommand: str):
    """Factory: creates a handler for a named movement subcommand."""
    def handler(task_id: str, params: dict,
                send_status: Callable) -> dict:
        duration = params.get("duration", 1.0)
        no_activate = params.get("no_activate", False)
        flag = " --no-activate" if no_activate else ""
        action_desc = subcommand.replace("-", " ")
        send_status("executing", 20.0,
                    f"Moving robot: {action_desc} for {duration}s...")
        return {
            "ok": True,
            "text": f"Robot {action_desc} for {duration}s.",
            "exec_command": f"{_ROBOT_SCRIPT}{flag} {subcommand} {duration}",
        }
    return handler


# Register all movement handlers
for _action, _subcmd in _MOVEMENT_HANDLERS.items():
    router.register(_action)(_make_movement_handler(_subcmd))


# ── Web Action Handlers ────────────────────────────────────────

@router.register("web_search")
def _handle_web_search(task_id: str, params: dict,
                       send_status: Callable) -> dict:
    query = params.get("query", "")
    count = params.get("count", 5)
    if not query:
        return {"ok": False, "text": "No search query provided."}
    send_status("searching", 30.0, f"Searching for: {query}")
    return {
        "ok": True,
        "text": f"Searching the web for: {query}",
        "requires_web_search": True,
        "query": query,
        "count": count,
    }


@router.register("web_fetch")
def _handle_web_fetch(task_id: str, params: dict,
                      send_status: Callable) -> dict:
    url = params.get("url", "")
    if not url:
        return {"ok": False, "text": "No URL provided."}
    send_status("fetching", 40.0, f"Fetching content from: {url}")
    return {
        "ok": True,
        "text": f"Fetching content from: {url}",
        "requires_web_fetch": True,
        "url": url,
    }


# ── Explore / Implement Handlers (Phase 3) ─────────────────────────

@router.register("explore")
def _handle_explore(task_id: str, params: dict,
                     send_status: Callable) -> dict:
    goal = params.get("goal", "")
    topic = params.get("topic", "general")
    context = params.get("context", "")

    send_status("researching", 10.0,
                f"Exploring: {goal}")

    return {
        "ok": True,
        "text": f"Exploring {topic}: {goal}",
        "requires_agent_exploration": True,
        "topic": topic,
        "goal": goal,
        "context": context,
    }


@router.register("implement")
def _handle_implement(task_id: str, params: dict,
                      send_status: Callable) -> dict:
    goal = params.get("goal", "")
    topic = params.get("topic", "general")
    context = params.get("context", "")
    attempt_id = params.get("attempt_id", 1)
    feedback = params.get("feedback")

    send_status("planning", 5.0,
                f"Planning implementation: {goal}")

    return {
        "ok": True,
        "text": f"Implementing {topic}: {goal}",
        "requires_agent_implementation": True,
        "topic": topic,
        "goal": goal,
        "context": context,
        "attempt_id": attempt_id,
        "feedback": feedback,
    }


# ── Camera / Display Handlers ──────────────────────────────────

@router.register("robot.take_photo_and_show")
def _handle_take_photo(task_id: str, params: dict,
                        send_status: Callable) -> dict:
    send_status("capturing", 30.0, "Taking a photo from the camera...")
    return {
        "ok": True,
        "text": "Photo captured and displayed on screen.",
        "exec_command": "python3 /home/ubuntu/minipupper-app/scripts/capture_and_show.py",
    }


@router.register("robot.show_image")
def _handle_show_image(task_id: str, params: dict,
                       send_status: Callable) -> dict:
    path = params.get("path", "/tmp/photo.jpg")
    send_status("displaying", 50.0, f"Displaying image: {path}")
    return {
        "ok": True,
        "text": f"Displaying image from {path}.",
        "exec_command": f"python3 /home/ubuntu/minipupper-app/scripts/capture_and_show.py --display-only {path}",
    }


# ── Query Handler ─────────────────────────────────────────────

@router.register("query")
def _handle_query(task_id: str, params: dict,
                  send_status: Callable) -> dict:
    question = params.get("question") or params.get("query", "")
    if not question:
        return {"ok": False, "text": "No question provided."}
    send_status("thinking", 20.0, "Thinking about your question...")
    return {
        "ok": True,
        "text": f"Answering: {question}",
        "requires_agent_reasoning": True,
        "question": question,
    }


# ── Main Handler ──────────────────────────────────────────────

async def handle_task_message(
    raw: dict,
    tracker: Optional[TaskTracker] = None,
    send_status_fn: Optional[SessionSendFn] = None,
    send_result_fn: Optional[SessionSendFn] = None,
    exec_fn: Optional[ExecFn] = None,
) -> dict:
    """Handle an incoming TaskMessage from the minipupper-app session.

    Args:
        raw: Raw dict from the session message (parsed JSON).
        tracker: Optional TaskTracker instance (uses singleton if None).
        send_status_fn: Callable to forward StatusMessage to the app session.
            Signature: (dict) -> Any.  The dict should be a serialised StatusMessage.
        send_result_fn: Callable to forward a ResultMessage to the app session.
            Signature: (dict) -> Any.
        exec_fn: Callable to run exec commands on the robot node.
            Required for robot actions; optional for web/query actions.
            Signature: (command, host, node) -> ExecResult.

    Returns:
        A result dict that the agent can use to determine next actions:
        {
            "ok": bool,
            "text": str,              # Human-readable summary
            "requires_web_search": bool,  # Agent should run web_search
            "requires_web_fetch": bool,   # Agent should run web_fetch
            "requires_agent_reasoning": bool,  # Agent should think/reply
            "exec_command": str | None,  # Command to run via exec on node
            "task_id": str,
        }
    """
    tracker = tracker or get_tracker()
    # Use no-op stubs if callbacks aren't provided
    _send_status = send_status_fn or (lambda d: None)
    _send_result = send_result_fn or (lambda d: None)

    # Validate protocol
    if not is_valid_message(raw):
        return {"ok": False, "text": "Invalid protocol message.", "task_id": ""}

    msg_type = raw.get("type", "")

    if msg_type == MSG_STATUS_QUERY:
        return handle_status_query(raw, tracker, _send_status)

    if msg_type != MSG_TASK:
        return {"ok": False, "text": f"Unknown message type: {msg_type}", "task_id": ""}

    # Parse the task request
    try:
        task_msg = TaskMessage.from_dict(raw)
    except Exception as e:
        return {"ok": False, "text": f"Failed to parse task: {e}", "task_id": ""}

    action = task_msg.action
    task_id = tracker.create_task(task_msg)

    # Helper: send a status update for this task
    def _send_progress(phase: str, progress: float, message: str, **extra):
        status = StatusMessage(
            taskId=task_id,
            phase=phase,
            progress=progress,
            message=message,
        )
        tracker.update_status(task_id, phase=phase, progress=progress,
                              message=message)
        _send_status(status.to_dict())

    # Find handler
    handler = router.get(action)
    if handler is None:
        tracker.update_status(task_id, phase="error", progress=0.0,
                              message=f"Unknown action: {action}")
        err_msg = f"Unknown action: '{action}'. Available: {', '.join(router.list_actions())}"
        result = ResultMessage(
            taskId=task_id,
            status="failed",
            error=err_msg,
        )
        _send_result(result.to_dict())
        return {"ok": False, "text": err_msg, "task_id": task_id}

    # Execute handler
    try:
        handler_result = handler(task_id, task_msg.params, _send_progress)
    except Exception as e:
        tb = traceback.format_exc()
        tracker.complete_task(task_id, result="", error=str(e))
        result_msg = ResultMessage(
            taskId=task_id,
            status="failed",
            error=str(e),
        )
        _send_result(result_msg.to_dict())
        return {
            "ok": False,
            "text": f"Handler error: {e}",
            "task_id": task_id,
            "error": str(e),
            "traceback": tb,
        }

    # If handler produced an exec_command, run it via exec_fn if available
    exec_command = handler_result.get("exec_command")
    if exec_command and exec_fn:
        _send_progress("executing", 60.0, f"Running: {exec_command}")
        try:
            exec_result = await exec_fn(
                command=exec_command,
                host="node",
                node="minipupper-deepseek",
            )
            tracker.update_status(task_id, phase="executed", progress=90.0,
                                  message="Command executed.")
        except Exception as e:
            tracker.complete_task(task_id, result="", error=str(e))
            result_msg = ResultMessage(
                taskId=task_id,
                status="failed",
                error=str(e),
            )
            _send_result(result_msg.to_dict())
            return {
                "ok": False,
                "text": f"Exec failed: {e}",
                "task_id": task_id,
                "error": str(e),
            }

    # Mark task complete if the handler doesn't require further agent/web work
    needs_more = any((
        handler_result.get("requires_web_search"),
        handler_result.get("requires_web_fetch"),
        handler_result.get("requires_agent_reasoning"),
        handler_result.get("requires_agent_exploration"),
        handler_result.get("requires_agent_implementation"),
    ))

    if not needs_more:
        final_text = handler_result.get("text", "Done.")
        tracker.complete_task(task_id, result=final_text)
        result_msg = ResultMessage(
            taskId=task_id,
            status="completed",
            result=final_text,
        )
        _send_result(result_msg.to_dict())

    return {
        "ok": True,
        "text": handler_result.get("text", "Task handled."),
        "task_id": task_id,
        **handler_result,  # Spread additional flags (requires_*, exec_command, etc.)
    }


# ── Status Query Handler ───────────────────────────────────────

def handle_status_query(
    raw: dict,
    tracker: Optional[TaskTracker] = None,
    send_status_fn: Optional[SessionSendFn] = None,
) -> dict:
    """Handle a status query from the app.

    Returns a summary of all active tasks.
    """
    tracker = tracker or get_tracker()
    _send_status = send_status_fn or (lambda d: None)

    all_tasks = tracker.get_all_tasks()
    active = [t for t in all_tasks if t.get("status") == "running"]

    if not active:
        text = "No active tasks."
    elif len(active) == 1:
        t = active[0]
        text = f"Working on: {t['message']} ({t['progress']:.0f}%)"
    else:
        text = f"{len(active)} active tasks. "
        text += "; ".join(f"{t['action']}: {t['message']}" for t in active)

    _send_status({
        "type": "event",
        "event": "status_summary",
        "payload": {
            "active_count": len(active),
            "total_tasks": len(all_tasks),
            "active": active,
            "summary": text,
        },
    })

    return {
        "ok": True,
        "text": text,
        "active_count": len(active),
        "total_tasks": len(all_tasks),
    }


# ── Convenience Senders ───────────────────────────────────────

def send_status(
    task_id: str,
    phase: str,
    progress: float,
    message: str,
    tracker: Optional[TaskTracker] = None,
    send_fn: Optional[SessionSendFn] = None,
):
    """Build and dispatch a StatusMessage."""
    tracker = tracker or get_tracker()
    tracker.update_status(task_id, phase=phase, progress=progress, message=message)
    msg = StatusMessage(taskId=task_id, phase=phase, progress=progress, message=message)
    if send_fn:
        send_fn(msg.to_dict())


def send_result(
    task_id: str,
    status: str,
    result: str,
    error: Optional[str] = None,
    tracker: Optional[TaskTracker] = None,
    send_fn: Optional[SessionSendFn] = None,
):
    """Build and dispatch a ResultMessage."""
    tracker = tracker or get_tracker()
    tracker.complete_task(task_id, result=result, error=error)
    msg = ResultMessage(taskId=task_id, status=status, result=result, error=error)
    if send_fn:
        send_fn(msg.to_dict())


# ── Agent Listener Guide (docstring, not code) ─────────────────

def _listener_guide():
    """
    === How the Main Agent Processes minipupper-app Messages ===

    The minipupper-app sends structured JSON messages to the "minipupper-app"
    Gateway session (via sessions.send). The agent should handle these during
    heartbeat polls or as part of its message-processing standing orders.

    1. Subscribe to minipupper-app session messages:

        sessions.messages.subscribe(sessionKey="minipupper-app")

    2. In your heartbeat or message handler, when you receive a session.message
       event for the minipupper-app session with a user message, check if it's
       a valid protocol message:

        from minipupper import parse_message, handle_task_message

        raw = parse_message(message_text)        # returns dict or None
        if raw:
            result = await handle_task_message(
                raw=raw,
                send_status_fn=send_via_gateway,
                send_result_fn=send_via_gateway,
                exec_fn=exec,                     # your exec tool
            )
            if result.get("requires_web_search"):
                # Agent runs web_search and sends result back
                await web_search(query=result["query"])
            if result.get("requires_web_fetch"):
                await web_fetch(url=result["url"])
            if result.get("requires_agent_reasoning"):
                # Agent responds directly (agent will see this naturally)
                pass
            if result.get("requires_agent_exploration"):
                # Agent explores robot capabilities (Phase 3)
                # - Runs exec commands on the Pi to test hardware/software
                # - Checks knowledge/INDEX.json for cached findings
                # - Writes findings to knowledge/{topic}.md
                # - Updates INDEX.json
                # - Calls send_result() with summary when done
                pass
            if result.get("requires_agent_implementation"):
                # Agent implements a new robot capability (Phase 3)
                # - Researches approach using knowledge base + web
                # - Writes code to custom/{topic}/main.py
                # - Tests on the Pi
                # - May set feedback_required=True for user evaluation
                # - Calls send_result() with results when done
                pass

    3. For robot-only tasks (init, move, etc.), the handler calls exec
       automatically and sends ResultMessage back to the app.

    4. For web/query tasks, the handler returns flags and the agent does the
       work, then calls send_result() manually when done.

    5. For explore/implement tasks (Phase 3), the handler returns flags and
       the agent does the work, then calls send_result() manually when done.

    Short version — add this to your heartbeat or standing orders:

        "When a session.message arrives for sessionKey 'minipupper-app',
         parse it with minipupper.parse_message(). If valid, call
         minipupper.handle_task_message() with the parsed dict,
         passing the exec tool as exec_fn."
    """
    pass