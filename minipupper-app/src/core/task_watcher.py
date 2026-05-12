import sys
import os
sys.path.insert(0, os.path.expanduser("~/minipupper-app/scripts"))  # noqa: E402
"""
Minipupper Phase 2 - Task File Watcher

Watches ~/minipupper-app/tasks.json for completed tasks from the OpenClaw agent.
When a task completes, injects the result into Gemini's conversation so it
can generate a natural TTS announcement for the user.

This replaces the complex session-based protocol with a simple shared file.

Protocol: The file at ~/minipupper-app/tasks.json is the shared task file.
- App writes tasks with status="pending"
- Agent updates status to "running" -> "completed" or "failed"
- This watcher detects completed tasks and triggers TTS
"""

import json
import logging
import os
import threading
import time
import uuid
from typing import Optional, List

from src.core.task_archiver import TaskArchiver

logger = logging.getLogger(__name__)

TASKS_FILE = os.path.expanduser("~/minipupper-app/tasks.json")
POLL_INTERVAL = 2.0  # Check file every 2 seconds


class TaskWatcher:
    def __init__(self, llm, audio_manager, announce_llm=None, on_result=None):
        self._task_display = None
        # Try to initialize the ST7789 LCD display for task status
        try:
            import sys as _sys
            import os as _os
            _sys.path.insert(0, _os.path.expanduser("~/minipupper-app/scripts"))
            from display_task_info import TaskDisplay
            self._task_display = TaskDisplay()
        except Exception:
            pass
        self.llm = llm  # main operator LLM (not used for announcements)
        self.announce_llm = announce_llm or llm  # dedicated LLM for announcements
        self.audio_manager = audio_manager
        self.archiver = TaskArchiver()
        self._on_result = on_result
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        # Track which task's progress announcement is being made (for interruption context)
        self._announcing_progress_task_id: Optional[str] = None
        self._announcing_progress_message: Optional[str] = None

    def start(self):
        # Archive any old completed tasks from previous sessions
        self._archive_old_completed()

        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="TaskWatcher")
        self._thread.start()
        logger.info("TaskWatcher started (polling %s every %.1fs)",
                     TASKS_FILE, POLL_INTERVAL)

    def _archive_old_completed(self):
        """Archive completed tasks from previous app sessions silently."""
        tasks = self._load_tasks()
        for task_id, task in tasks.items():
            if task.get("status") in ("completed", "failed"):
                task["announced"] = True
                try:
                    self.archiver.archive_task(task)
                    logger.info("TaskWatcher: archived stale task %s (%s) on startup",
                               task_id[:8], task.get("action", "?"))
                except Exception:
                    pass
        self._save_tasks(tasks)

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3.0)

    def _load_tasks(self) -> dict:
        if not os.path.exists(TASKS_FILE):
            return {}
        try:
            with open(TASKS_FILE) as f:
                data = json.load(f)
            # Handle wrapped format: {"tasks": {...}, "archived": [...]}
            if isinstance(data, dict) and "tasks" in data:
                return data["tasks"]
            # Legacy flat format: {"task-id": {...}, ...}
            if isinstance(data, dict):
                return data
            return {}
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("TaskWatcher: could not read tasks: %s", e)
            return {}

    def _save_tasks(self, tasks: dict):
        os.makedirs(os.path.dirname(TASKS_FILE), exist_ok=True)
        # Always write in wrapped format: {"tasks": {...}}
        # This keeps the file format consistent regardless of who writes it
        # (the gateway agent may also add "archived": [...] to the same file)
        wrapped = {"tasks": tasks}
        with open(TASKS_FILE, "w") as f:
            json.dump(wrapped, f, indent=2)

    def write_task(self, task_data: dict):
        """Write a new pending task to the file."""
        task_ids = self.write_tasks([task_data])
        return task_ids[0] if task_ids else None

    def write_tasks(self, task_items: List[dict]) -> List[str]:
        """Write one or more new pending tasks to the file."""
        if not task_items:
            return []

        task_ids: List[str] = []
        with self._lock:
            tasks = self._load_tasks()
            for task_data in task_items:
                task_id = task_data.get("taskId") or f"task-{uuid.uuid4().hex[:12]}"
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
                    "announced": False,
                    "createdAt": time.time(),
                    "updatedAt": time.time(),
                }
                task_ids.append(task_id)
            self._save_tasks(tasks)

        if len(task_ids) == 1:
            logger.info("TaskWatcher: wrote pending task %s (%s)",
                        task_ids[0][:8], task_items[0].get("action"))
        else:
            logger.info("TaskWatcher: wrote %d pending tasks %s",
                        len(task_ids), ", ".join(task_id[:8] for task_id in task_ids))
        return task_ids

    def _announce_progress(self, task: dict):
        """Announce a progress update using the dedicated announce LLM."""
        phase = task.get("phase", "")
        progress = task.get("progress", 0)
        message = task.get("message", "")
        action = task.get("action", "")
        task_id = task.get("taskId", "")

        # Remember what we're about to announce (for interruption context later)
        self._announcing_progress_task_id = task_id
        self._announcing_progress_message = message or f"{action} progress at {progress:.0f}%"

        # Generate announcement using the dedicated announce LLM
        announcement = message if message and len(message) > 3 else f"{action.replace('_', ' ')}: {progress:.0f}% done"

        logger.info("TaskWatcher: announcing progress: %s", announcement[:100])
        if self.audio_manager:
            try:
                completed = self.audio_manager.speak(announcement)
            except Exception as e:
                logger.error("TaskWatcher: TTS error: %s", e)

        # Clear tracking after announcement finishes (or was interrupted)
        if self._announcing_progress_task_id == task_id:
            self._announcing_progress_task_id = None
            self._announcing_progress_message = None

    def _announce_result(self, task: dict):
        """Announce task result — interrupts progress, uses LLM, gated on TTS.

        - Interrupts any in-progress speech immediately
        - If a progress announcement for this same task was interrupted,
          tells the LLM about the interruption context
        - Only marks announced=True after TTS successfully completes
        """
        action = task.get("action", "unknown")
        result = task.get("result", "")
        error = task.get("error")
        user_query = task.get("userQuery", "")
        task_id = task.get("taskId", "unknown")

        # ── 1. INTERRUPT any in-progress speech ──────────────────
        progress_was_interrupted = False
        interrupted_message = ""
        was_playing = False
        if self.audio_manager:
            try:
                was_playing = True
                self.audio_manager.interrupt_speech()
                import time as _t
                _t.sleep(0.05)  # tiny settle for audio pipeline
            except Exception:
                was_playing = False

        # ── 2. Check if we were just announcing progress for this task ──
        if (self._announcing_progress_task_id == task_id
                and self._announcing_progress_message):
            progress_was_interrupted = True
            interrupted_message = self._announcing_progress_message
            logger.info("TaskWatcher: progress for %s was interrupted by result",
                        task_id[:8])

        self._announcing_progress_task_id = None
        self._announcing_progress_message = None

        # ── 3. GENERATE announcement text (own LLM, no thread contention) ──
        if error:
            # Short path: don't bother LLM for errors
            announcement = f"Sorry, there was an error: {error}"
        else:
            # Build LLM prompt with interruption context if available
            prompt_parts = []
            if progress_was_interrupted:
                prompt_parts.append(
                    "The previous progress announcement was interrupted "
                    "because the task completed. "
                    "Progress that was interrupted: '" + interrupted_message + "'"
                )
            if action in ("web_search", "web_fetch", "query"):
                action_label = action.replace('_', ' ')
                prompt_parts.append(
                    "The task was: " + action_label + ". "
                    "The user asked about: '" + user_query + "'. "
                    "Result: " + result + ". "
                    "Summarize briefly and naturally in 1-2 sentences."
                )
            else:
                action_label = action.replace("_", " ").replace("robot", "").strip()
                prompt_parts.append(
                    "The task '" + action_label + "' completed. "
                    + ("Result: " + result if result else "")
                )

            prompt = "\n".join(prompt_parts)

            try:
                from src.core.llm_engine import Message
                messages = [
                    Message(role="system", content=(
                        "You are a concise status announcer for a robot assistant. "
                        "Keep responses under 2 sentences. Sound natural and helpful. "
                        "Speak as if you are the robot itself."
                    )),
                    Message(role="user", content=prompt),
                ]
                announcement = self.announce_llm.generate_response(
                    messages=messages, max_tokens=100
                )
            except Exception as e:
                logger.warning("TaskWatcher: LLM announcement failed: %s", e)
                announcement = result if result else f"{action.replace('_', ' ')} completed."

        logger.info("TaskWatcher: announcing result: %s", announcement[:200])

        # ── 4. SPEAK via TTS ──────────────────────────────────────
        tts_succeeded = False
        if self.audio_manager:
            try:
                completed = self.audio_manager.speak(announcement)
                if completed:
                    tts_succeeded = True
                else:
                    logger.info("TaskWatcher: result interrupted by user, will retry once")
                    import time as _t
                    _t.sleep(1.0)
                    try:
                        completed = self.audio_manager.speak(announcement)
                        if completed:
                            tts_succeeded = True
                    except Exception:
                        pass
            except Exception as e:
                logger.error("TaskWatcher: TTS error: %s", e)

        # ── 5. Only mark announced after successful TTS ────────────
        if tts_succeeded:
            self._mark_announced(task_id)

            # Phase 3: Notify operator of completed task result
            if self._on_result:
                try:
                    self._on_result(task)
                except Exception as _e:
                    logger.warning("TaskWatcher: on_result callback failed: %s", _e)

            logger.info("TaskWatcher: archiving task %s for history", task_id[:8])
            try:
                self.archiver.archive_task(task)
            except Exception as e:
                logger.warning("TaskWatcher: archive failed: %s", e)
        else:
            logger.warning(
                "TaskWatcher: TTS failed for task %s, leaving announced=False for retry",
                task_id[:8])

    def _mark_announced(self, task_id: str):
        """Set announced=True on a completed task so cron cleanup can archive it."""
        tasks = self._load_tasks()
        if task_id in tasks:
            tasks[task_id]["announced"] = True
            tasks[task_id]["updatedAt"] = time.time()
            self._save_tasks(tasks)
            logger.info("TaskWatcher: marked task %s as announced", task_id[:8])

    def _update_display(self, tasks: dict):
        """Update the LCD display with the most interesting task state."""
        if not self._task_display:
            return

        try:
            import time as _t
            # Find the most interesting task: running > pending > completed > idle
            display_task = None
            priority = -1
            for tid, task in tasks.items():
                s = task.get("status", "")
                p = {"running": 3, "pending": 2, "completed": 1, "failed": 1}.get(s, 0)
                if p > priority:
                    priority = p
                    display_task = task

            if display_task and priority > 0:
                self._task_display.show_task(
                    action=display_task.get("action", ""),
                    status=display_task.get("status", "idle"),
                    phase=display_task.get("phase", ""),
                    progress=display_task.get("progress", 0),
                    message=display_task.get("message", ""),
                    time_str=_t.strftime("%H:%M"),
                )
            else:
                self._task_display.show_idle()
        except Exception:
            pass  # Don't crash if display fails

    def _run(self):
        # Track last announced progress per task
        _last_announced: dict = {}
        while not self._stop.is_set():
            try:
                tasks = self._load_tasks()
                # Update LCD display with current task state
                self._update_display(tasks)
                for task_id, task in tasks.items():
                    status = task.get("status", "")
                    prev = _last_announced.get(task_id, {})

                    # Completed/failed tasks: only announce if not already announced
                    if status in ("completed", "failed") and not task.get("announced"):
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
