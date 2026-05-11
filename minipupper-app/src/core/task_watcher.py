"""
Minipupper Phase 2 - Task File Watcher

Watches ~/minipupper-app/tasks.json for completed tasks from the OpenClaw agent.
When a task completes, injects the result into Gemini's conversation so it
can generate a natural TTS announcement for the user.

This replaces the complex session-based protocol with a simple shared file.

Protocol: The file at ~/minipupper-app/tasks.json is the shared task file.
- App writes tasks with status="pending"
- Agent updates status to "running" → "completed" or "failed"
- This watcher detects completed tasks and triggers TTS
"""

import json
import logging
import os
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

TASKS_FILE = os.path.expanduser("~/minipupper-app/tasks.json")
POLL_INTERVAL = 2.0  # Check file every 2 seconds


class TaskWatcher:
    """Background thread that watches tasks.json for completed tasks."""

    def __init__(self, llm, audio_manager):
        self.llm = llm
        self.audio_manager = audio_manager
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_checked_tasks: set = set()

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="TaskWatcher"
        )
        self._thread.start()
        logger.info("TaskWatcher started (polling %s every %.1fs)",
                     TASKS_FILE, POLL_INTERVAL)

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3.0)

    def _load_tasks(self) -> dict:
        if not os.path.exists(TASKS_FILE):
            return {}
        try:
            with open(TASKS_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("TaskWatcher: could not read tasks: %s", e)
            return {}

    def _save_tasks(self, tasks: dict):
        os.makedirs(os.path.dirname(TASKS_FILE), exist_ok=True)
        with open(TASKS_FILE, "w") as f:
            json.dump(tasks, f, indent=2)

    def write_task(self, task_data: dict):
        """Write a new pending task to the file."""
        tasks = self._load_tasks()
        task_id = task_data.get("taskId", f"task-{int(time.time())}")
        tasks[task_id] = {
            "taskId": task_id,
            "action": task_data.get("action", ""),
            "params": task_data.get("params", {}),
            "userQuery": task_data.get("userQuery", ""),
            "status": "pending",
            "phase": "queued",
            "progress": 0,
            "message": "Waiting for agent...",
            "result": None,
            "error": None,
            "createdAt": time.time(),
            "updatedAt": time.time(),
        }
        self._save_tasks(tasks)
        # NOT added to _last_checked_tasks — we detect completion by status change
        logger.info("TaskWatcher: wrote pending task %s (%s)",
                     task_id[:8], task_data.get("action"))

    def _announce_progress(self, task: dict):
        """Use Gemini to generate a brief progress TTS announcement."""
        phase = task.get("phase", "")
        progress = task.get("progress", 0)
        message = task.get("message", "")
        action = task.get("action", "")

        prompt = (
            f"The OpenClaw agent is making progress on a {action} task: "
            f"{message} (phase: {phase}, {progress:.0f}% complete). "
            f"Generate a brief, natural progress update for the user."
        )

        try:
            from src.core.llm_engine import Message
            messages = [
                Message(role="system", content=(
                    "You are a concise progress announcer for a robot. "
                    "Keep responses under 10 words. Sound natural."
                )),
                Message(role="user", content=prompt),
            ]
            announcement = self.llm.generate_response(
                messages=messages, max_tokens=50
            )
        except Exception as e:
            logger.warning("TaskWatcher: progress LLM failed: %s", e)
            announcement = message if len(message) > 3 else f"Working on {action}..."

        logger.info("TaskWatcher: announcing progress: %s", announcement[:100])
        if self.audio_manager:
            try:
                completed = self.audio_manager.speak(announcement)
                if not completed:
                    logger.info("TaskWatcher: progress interrupted")
            except Exception as e:
                logger.error("TaskWatcher: TTS error: %s", e)

    def _announce_result(self, task: dict):
        """Use Gemini to generate a TTS announcement for a task result."""
        action = task.get("action", "unknown")
        result = task.get("result", "")
        error = task.get("error")
        user_query = task.get("userQuery", "")

        if error:
            prompt = (
                f"The OpenClaw agent attempted to handle a request to {action} "
                f"but encountered an error: {error}. "
                f"The user's request was: '{user_query}'. "
                f"Briefly apologize and explain the issue."
            )
        else:
            prompt = (
                f"The OpenClaw agent completed a request to {action}. "
                f"Result: {result}. "
                f"The user's request was: '{user_query}'. "
                f"Summarize the result briefly and naturally for the user."
            )

        try:
            from src.core.llm_engine import Message
            messages = [
                Message(role="system", content=(
                    "You are a concise status announcer for a robot operator. "
                    "Keep responses under 2 sentences. Sound natural and helpful."
                )),
                Message(role="user", content=prompt),
            ]
            announcement = self.llm.generate_response(
                messages=messages, max_tokens=100
            )
        except Exception as e:
            logger.warning("TaskWatcher: LLM announcement failed: %s", e)
            announcement = result if result else f"Task {action} completed."

        logger.info("TaskWatcher: announcing result: %s", announcement[:200])
        if self.audio_manager:
            try:
                completed = self.audio_manager.speak(announcement)
                if not completed:
                    logger.info("TaskWatcher: announcement interrupted")
            except Exception as e:
                logger.error("TaskWatcher: TTS error: %s", e)

    def _run(self):
        # Track last announced progress per task
        _last_announced: dict = {}
        while not self._stop.is_set():
            try:
                tasks = self._load_tasks()
                for task_id, task in tasks.items():
                    status = task.get("status", "")
                    prev = _last_announced.get(task_id, {})

                    # Completed/failed tasks: always announce once
                    if status in ("completed", "failed") and task_id not in self._last_checked_tasks:
                        self._last_checked_tasks.add(task_id)
                        _last_announced[task_id] = task
                        logger.info("TaskWatcher: detected completed task %s",
                                     task_id[:8])
                        self._announce_result(task)

                    # Progress updates: only announce meaningful changes
                    elif status == "running":
                        cur_progress = task.get("progress", 0)
                        cur_phase = task.get("phase", "")
                        cur_msg = task.get("message", "")
                        prev_progress = prev.get("progress", -1)
                        prev_phase = prev.get("phase", "")
                        prev_msg = prev.get("message", "")

                        # Announce if phase changed, progress jumped 20%+, or message changed significantly
                        progress_jump = cur_progress - prev_progress >= 20
                        phase_changed = cur_phase and cur_phase != prev_phase
                        msg_changed = cur_msg and cur_msg != prev_msg and len(cur_msg) > 3

                        if progress_jump or phase_changed or msg_changed:
                            _last_announced[task_id] = task
                            logger.info("TaskWatcher: progress update for %s: %s %.0f%% - %s",
                                         task_id[:8], cur_phase, cur_progress, cur_msg[:50])
                            self._announce_progress(task)

                time.sleep(POLL_INTERVAL)
            except Exception as e:
                logger.warning("TaskWatcher: error in poll loop: %s", e)
                time.sleep(POLL_INTERVAL)
