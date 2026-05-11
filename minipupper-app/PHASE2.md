# Phase 2 - OpenClaw Agent Integration

**Protocol Version:** minipupper-v1  
**Last Updated:** 2026-05-11  
**Status:** Active Development

---

## Overview

Phase 2 connects the Minipupper Operator app's Gemini LLM to the OpenClaw
agent for complex task offloading. Gemini decides which tasks need the agent's
tool use (web search, robot control, file operations) and offloads them via
a shared JSON file on the Pi's filesystem.

## File-Based Protocol (Not Session-Based)

The protocol uses a **shared JSON file** (`~/minipupper-app/tasks.json`) as
the communication channel between the app and the OpenClaw agent. This avoids
the complexity and race conditions of session-based message passing.

### Why File-Based?

- **No session pollution** — messages don't appear in agent chat history
- **No race conditions** — the `announced` flag prevents conflicts
- **Debuggable** — you can `cat tasks.json` at any time to see the state
- **No startup overhead** — no isolated agent cold starts
- **Clean monitoring** — completed tasks auto-archive from the main file

---

## Architecture

```
User speaks → ASR → Gemini LLM
  ├─ Simple requests → handle locally (TTS response)
  └─ Complex tasks → Gemini outputs [TASK]{...}[/TASK]
                     → App extracts JSON, writes to tasks.json (status: "pending")
                     ↓
                ┌─────────────────────────────────────────────┐
                │          tasks.json (shared file)            │
                │  task-xxx: { status, progress, result,       │
                │             announced, ... }                 │
                └─────────────────────────────────────────────┘
                     ↓ (cron polls every 5s)
                ┌─────────────────────────────────────────────┐
                │  OpenClaw Gateway Agent                      │
                │  • Reads pending tasks via node exec         │
                │  • web_search → web_search tool             │
                │  • web_fetch → web_fetch tool               │
                │  • robot.* → exec on node                   │
                │  • Writes result back as "completed"         │
                └─────────────────────────────────────────────┘
                     ↓
                status: "completed", announced: false
                     ↓
                ┌─────────────────────────────────────────────┐
                │  TaskWatcher (app, polls every 2s)           │
                │  • Detects completed + !announced            │
                │  • Gemini generates TTS announcement         │
                │  • Sets announced: true                      │
                │  • Archives for history (non-destructive)    │
                └─────────────────────────────────────────────┘
                     ↓
                TTS: "Beijing is 22°C and clear today!"
```

---

## Task Lifecycle

A task moves through these states:

```
[App writes] → status: "pending",  announced: false
[Cron picks up] → status: "running",  progress: 30,  announced: false
[Cron processing] → status: "running",  progress: 60,  announced: false  
[Cron done] → status: "completed",  result: "...",  announced: false
[TaskWatcher announces] → announced: true (status unchanged)
[Cron cleanup] → removed from tasks.json, archived to tasks_archive/
```

---

## Files Involved

### `~/minipupper-app/tasks.json` — Active task file

```json
{
  "task-1778486544": {
    "taskId": "task-1778486544",
    "action": "web_search",
    "params": { "query": "weather in Beijing" },
    "userQuery": "",
    "status": "pending",
    "phase": "queued",
    "progress": 0,
    "message": "Waiting for agent...",
    "result": null,
    "error": null,
    "announced": false,
    "createdAt": 1778486544.855,
    "updatedAt": 1778486544.855
  }
}
```

### `~/minipupper-app/tasks_archive/` — Archived task storage

Date-partitioned archive files (e.g., `2026-05-11.json`).

### `~/minipupper-app/tasks_archive.json` — Archive index

Metadata about all archived tasks for quick lookups.

---

## System Prompt Markers

Gemini indicates task offloading by wrapping JSON in `[TASK]...[/TASK]` markers
in its response. The app detects these markers and writes the task to the file.

Example Gemini output:
```
Let me look that up!
[TASK]
{"protocol":"minipupper-v1","type":"task","action":"web_search","params":{"query":"weather in Hong Kong"}}
[/TASK]
```

The text before `[TASK]` is spoken immediately ("Let me look that up!").
The task is written to the file for the agent to process.

---

## Components (App Side)

| File | Purpose |
|------|---------|
| `src/core/task_watcher.py` | Polls `tasks.json` every 2s, announces completed tasks via Gemini+TTS |
| `src/core/task_archiver.py` | Archives completed tasks to date-partitioned storage |
| `config/system_prompt_phase2.txt` | Enhanced Gemini prompt with offloading instructions |
| `minipupper_operator.py` | Detects `[TASK]` markers, writes tasks to file, sends notification |

## Components (Gateway Side)

| File | Purpose |
|------|---------|
| `~/.openclaw/workspace/minipupper/task_handler.py` | 19-action router for task processing |
| `~/.openclaw/workspace/minipupper/protocol.py` | Protocol message types and parsers |
| `~/.openclaw/workspace/minipupper/status_push.py` | Manual task status reporter |
| `HEARTBEAT.md` | Heartbeat instructions for pending task processing |

## Available Actions

| Action | Tool | Description |
|--------|------|-------------|
| `web_search` | web_search | Search the web for information |
| `web_fetch` | web_fetch | Fetch content from a URL |
| `robot.init` | exec on node | Activate robot + raise body |
| `robot.deactivate` | exec on node | Reset and deactivate robot |
| `robot.move_forward` | exec on node | Move forward (params: duration) |
| `robot.move_backward` | exec on node | Move backward |
| `robot.strafe_right` | exec on node | Strafe right |
| `robot.strafe_left` | exec on node | Strafe left |
| `robot.rotate_cw` | exec on node | Rotate clockwise |
| `robot.rotate_ccw` | exec on node | Rotate counter-clockwise |
| `robot.dance` | exec on node | Dance sequence |
| `robot.reset` | exec on node | Full reset sequence |
| `robot.stop` | exec on node | Stop all movement |
| `robot.look_up` | exec on node | Pitch body up |
| `robot.look_down` | exec on node | Pitch body down |
| `robot.raise_body` | exec on node | Increase body height |
| `robot.lower_body` | exec on node | Decrease body height |

---

## Monitoring

From the Pi terminal:

```bash
# Current task state
cat ~/minipupper-app/tasks.json

# Archive stats
python scripts/manage_archives.py stats

# Recent completed tasks
python scripts/manage_archives.py recent --limit 10
```

From the gateway terminal:

```bash
# Streaming gateway logs
openclaw logs --follow --json | grep -i minipupper
```

---

## Architecture Decisions

### Why not session-based?

The initial Phase 2 design used Gateway sessions for communication:
- App sent tasks to a shared session via `sessions.send` RPC
- Agent polled the session for new messages
- This caused: session pollution, stale message replay, "skipped" spam loops

The file-based approach eliminates all of these issues.

### Why the `announced` flag?

Without it, the TaskWatcher would need to track announced task IDs in memory,
which is lost on restart. The `announced` flag persists in the file so:
- Across restarts, already-announced tasks aren't re-announced
- The cron can safely clean up announced+completed tasks
- Monitoring shows a clean `tasks.json` with only active tasks

### Why both cron and TaskWatcher?

The cron (every 5s on the gateway) handles task execution (web search, robot
control). The TaskWatcher (every 2s on the app) handles announcement. They
write different fields: cron writes `status`/`result`, TaskWatcher writes
`announced`. No race because cron only touches "pending" tasks and the cron
cleans up after completion.
