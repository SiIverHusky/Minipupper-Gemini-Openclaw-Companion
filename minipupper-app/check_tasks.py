#!/usr/bin/env python3
"""Check the status of Phase 2 tasks from the Pi terminal."""
import json
import os

TASKS_FILE = os.path.expanduser(
    "~/.openclaw/workspace/minipupper/tasks.json"
)

if not os.path.exists(TASKS_FILE):
    print("No tasks file found. The gateway may need to process a task first.")
    print(f"(expected at: {TASKS_FILE})")
    exit(1)

with open(TASKS_FILE) as f:
    tasks = json.load(f)

if not tasks:
    print("No tasks recorded.")
    exit(0)

for task_id, task in tasks.items():
    status = task.get("status", "unknown")
    action = task.get("action", "unknown")
    phase = task.get("phase", "")
    progress = task.get("progress", 0)
    message = task.get("message", "")
    result = task.get("result", "")
    error = task.get("error", "")

    icon = {"running": "🔄", "completed": "✅", "failed": "❌"}.get(status, "❓")
    print(f"{icon} [{task_id[:8]}] {action}")
    print(f"   Status: {status}")
    if phase:
        print(f"   Phase: {phase}")
    print(f"   Progress: {progress:.0f}%")
    print(f"   Message: {message}")
    if result:
        print(f"   Result: {result[:200]}")
    if error:
        print(f"   Error: {error[:200]}")
    print()
