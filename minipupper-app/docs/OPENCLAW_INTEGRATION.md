# OpenClaw Gateway Integration — Minipupper App

**Status:** Active — Phase 2  
**Last Updated:** 2026-05-11

---

## Architecture Overview

The system has two machines on a shared Tailscale network:

- **Cloud server** (`instance-20260506-083731.tail2df607.ts.net`) — runs the OpenClaw Gateway 
- **Raspberry Pi** (`minipupperv2`) — runs the node service + `minipupper-app` voice frontend

```
┌─────────────────────────┐     Tailscale TLS      ┌──────────────────────────┐
│   Cloud Server           │◀──────────────────────▶│   Raspberry Pi            │
│                          │                        │   (minipupperv2)          │
│  OpenClaw Gateway        │                        │                           │
│  ws://127.0.0.1:18789    │                        │  openclaw node run       │
│                          │                        │  (node: minipupper-      │
│  Agent Sessions:         │                        │   deepseek)               │
│  • main (heartbeat 5s)   │                        │                           │
│  • dashboard (WebChat)   │                        │  minipupper-app           │
│  • minipupper-app        │                        │  (voice frontend)         │
│    (stable session)      │                        │  ┌─────────────────────┐  │
│                          │                        │  │ ASR (Google Cloud)  │  │
│  Cron: 5s isolated       │                        │  │ TTS (Google Cloud)  │  │
│  (process tasks.json)    │                        │  │ Gemini 2.5 Flash    │  │
│                          │                        │  │ Barge-in detect     │  │
│                          │                        │  │ TaskWatcher (2s)    │  │
│                          │                        │  │ TaskArchiver        │  │
│                          │                        │  │ WS operator client  │──┼──wss://...:443
│                          │                        │  └─────────────────────┘  │
│                          │                        │                           │
│                          │                        │  tasks.json (shared)      │
│                          │                        │  tasks_archive/           │
└─────────────────────────┘                        └──────────────────────────┘
```

## Communication Protocol

### Phase 2: File-Based (Current)

The app and Gateway agent communicate via a shared JSON file on the Pi:

1. **App writes** task to `~/minipupper-app/tasks.json` (status: "pending")
2. **Cron** (every 5s) reads file via node exec, processes pending tasks
3. **Cron writes** result back (status: "completed", result: "...")
4. **TaskWatcher** (polls every 2s) detects completion, announces via Gemini+TTS
5. **TaskWatcher** sets `announced: true`
6. **Cron** cleans up announced+completed tasks from main file, archives to history

### Files

| File | Location | Purpose |
|------|----------|---------|
| `tasks.json` | Pi: `~/minipupper-app/` | Active task file (app ↔ agent) |
| `tasks_archive/` | Pi: `~/minipupper-app/` | Date-partitioned archive |
| `tasks_archive.json` | Pi: `~/minipupper-app/` | Archive index |

### Task States

```
pending → running (with progress) → completed (with result)
                                       → announced (flag set)
                                       → archived (removed from active file)
```

### Task Format

```json
{
  "task-123": {
    "taskId": "task-123",
    "action": "web_search",
    "params": { "query": "weather Hong Kong" },
    "status": "completed",
    "progress": 100,
    "message": "Search complete",
    "result": "29°C, partly cloudy...",
    "announced": true,
    "createdAt": 1778483365.956,
    "updatedAt": 1778483365.956
  }
}
```

## Gateway Configuration

### Heartbeat (for task processing)
- Interval: 5s
- Session: main
- Reads `HEARTBEAT.md` for instructions

### Cron (for task execution)
- Interval: 5s
- Session: isolated agent turn
- Delivery: none (no messages sent)
- Purpose: Execute pending tasks (web_search, robot.*, etc.)

### Node Connection
```bash
openclaw node run --host "instance-20260506-083731.tail2df607.ts.net" \
  --port 443 --tls --display-name "minipupper-deepseek"
```

## Monitoring

### From Pi Terminal
```bash
# Current task state
cat ~/minipupper-app/tasks.json

# Archive statistics
python ~/minipupper-app/scripts/manage_archives.py stats

# Recent history
python ~/minipupper-app/scripts/manage_archives.py recent --limit 20
```

### From Gateway Terminal
```bash
# Live logs
openclaw logs --follow --json | grep -i minipupper

# Session list
openclaw sessions list
```

## App Connection

The app connects as an **operator** client to the Gateway over Tailscale TLS:

```python
from src.openclaw.client import OpenClawClient

client = OpenClawClient(
    gateway_url="wss://instance-20260506-083731.tail2df607.ts.net:443",
    session_target="main"  # or a specific session key
)
client.start(message_handler)
```

The app subscribes to session messages and can also send messages via
`sessions.send` RPC. In Phase 2, this is primarily used for:
- Subscribing to session updates
- Sending "task_written" notifications to wake the agent

## Pairing & Approval

First connect requires pairing:

```bash
# On the cloud server: approve the device
openclaw devices approve <request-id>
```

## Task History

Completed tasks are automatically archived to `~/minipupper-app/tasks_archive/`
and removed from the active `tasks.json`. The archive is date-partitioned:

```
tasks_archive/
├── 2026-05-11.json
├── 2026-05-12.json
└── ...
```

Use the CLI tool to query:

```bash
python ~/minipupper-app/scripts/manage_archives.py stats
python ~/minipupper-app/scripts/manage_archives.py recent --limit 20
```
