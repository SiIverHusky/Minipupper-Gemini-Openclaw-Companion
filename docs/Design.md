# OpenClaw Voice Companion — Design Document

> **Status:** Draft
> **Date:** 2026-05-09
> **Authors:** You + OpenClaw
> **Project:** Voice-first companion app that delegates tool execution to OpenClaw

---

## 1. Overview

A dual-component system where a **voice companion app** handles real-time speech I/O and conversational fast-turnaround, while **OpenClaw** handles heavy tool orchestration (browser automation, web search, robot control, etc.).

### Why Two Components?

| Concern | Companion App | OpenClaw |
|---|---|---|
| Latency sensitivity | High (voice → user in <1s) | Low (async tool execution) |
| Compute needed | Light (small LLM + ASR/TTS) | Heavy (tool orchestration, large context) |
| Where it runs | Locally / edge | Server / same host / remote |
| State | Short-lived, conversational | Long-lived, task-oriented |

---

## 2. High-Level Architecture

```
┌──────────────────────────────────────────────────┐
│                  USER (Voice)                     │
└─────────┬───────────────────────────┬────────────┘
          │ ASR (speech→text)         │ TTS (text→speech)
          ▼                           ▲
┌──────────────────────────────────────────────────────┐
│              COMPANION APP (Voice Frontend)           │
│                                                      │
│  ┌───────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ ASR Engine │  │  TTS     │  │ Companion LLM     │  │
│  │ (Whisper   │  │ Engine   │  │ (fast local       │  │
│  │  local/api)│  │ (Piper / │  │  model, small     │  │
│  │           │  │  Eleven)  │  │  context)          │  │
│  └───────────┘  └──────────┘  └────────┬───────────┘  │
│                                        │              │
│  ┌──────────────────────────────────────▼────────────┐ │
│  │              Task Router                           │ │
│  │  (classifies intent: delegate to OpenClaw or       │ │
│  │   handle conversationally)                        │ │
│  └──────────────────────┬───────────────────────────┘ │
└─────────────────────────┼─────────────────────────────┘
                          │ REST / WebSocket / Webhook
                          ▼
┌──────────────────────────────────────────────────────┐
│              OPENCLAW (Tool Backend)                   │
│                                                      │
│  ┌──────────────────────────────────────────────────┐ │
│  │  Agent Runtime (main session or sub-agent)       │ │
│  │  • Web search / fetch                            │ │
│  │  • Browser automation                            │ │
│  │  • Mini Pupper robot control                     │ │
│  │  • File system / code execution                  │ │
│  │  • Scheduled tasks / reminders                   │ │
│  └──────────────────────────────────────────────────┘ │
│                                                      │
│  ┌──────────────────────────────────────────────────┐ │
│  │  Status Reporter                                  │ │
│  │  (emits task progress to companion app)           │ │
│  └──────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────┘
```

---

## 3. Component Details

### 3.1 Companion App

#### ASR Engine
- **Primary:** Whisper (local, `whisper.cpp` or `faster-whisper`)
- **Fallback:** Cloud ASR API if local GPU unavailable
- **Mode:** Streaming (output partial hypotheses for lower latency)
- **Wake word / push-to-talk** configurable

#### TTS Engine
- **Primary:** Piper TTS (local, fast, good quality)
- **Premium:** ElevenLabs (lower latency + voice quality, requires API key)
- **Modes:** Interruptible (new utterance can cut off current TTS)
- **Queue:** Speech queue for batching progress updates into natural chunks

#### Companion LLM
- **Role:** Conversation manager, lightweight reasoning, status narration
- **Model requirements:** Fast inference (<200ms response), small context (4-8K tokens)
- **Candidates:** Llama 3.2 3B, Phi-4, Qwen 2.5 7B, or Mistral 7B
- **Quantization:** 4-bit or 8-bit for local CPU/edge NPU
- **Prompts:** Two system prompt modes:
  - **Conversational mode** — chat with user, no tool delegation
  - **Task delegation mode** — constructs structured task request for OpenClaw

#### Task Router

The companion LLM classifies each user utterance into one of:

| Intent | Action |
|---|---|
| `converse` | Respond directly, no OpenClaw delegation |
| `delegate` | Parse task → structured request → send to OpenClaw |
| `status_check` | Query OpenClaw for task status → summarize to user |
| `interrupt` | Cancel active task (stop OpenClaw exec, clear queue) |

**Routing prompt** (compressed classifier, not full LLM):

```
Given user utterance, classify intent:
- converse: greeting, opinion, small talk, personal questions
- delegate: action requests (search, browse, control robot, compute, etc.)
- status_check: "how's it going?", "what's taking so long?", "any updates?"
- interrupt: "stop", "cancel", "never mind", "forget it"
```

---

### 3.2 OpenClaw (Existing System)

#### Task Listener Interface
OpenClaw needs a listener endpoint to accept incoming tasks. Candidates:

- **REST API:** `POST /api/tasks` with task payload → returns `taskId`
- **WebSocket:** Persistent connection, bidirectional streaming
- **Webhook subscription:** Companion app registers webhook URL for status callbacks

#### Task Execution
- Main session or isolated sub-agent per task
- Parallel task support (multiple delegations in flight)
- Tool access: web search, fetch, browser (via browser-automation skill), robot control (via minipupper-control skill), cron, file I/O

#### Status Reporter

OpenClaw emits structured status updates during task execution:

```
{
  "taskId": "uuid",
  "sequence": 1,
  "status": "in_progress",
  "stage": "searching_web",
  "detail": "Searching for mini pupper ROS troubleshooting guides...",
  "timestamp": "2026-05-09T08:33:00Z"
}
```

Status events to emit:
- `accepted` — task received and queued
- `in_progress` — actively working (with stage/detail)
- `tool_invocation` — specific tool being called (e.g., "using browser to navigate to URL")
- `partial_result` — intermediate data available
- `completed` — final result
- `failed` — error with message
- `cancelled` — user interrupted

---

## 4. Communication Protocol

### 4.1 Transport

**Primary:** WebSocket (companion app as client, OpenClaw as server)
**Fallback:** REST polling (companion polls `GET /api/tasks/:taskId/status`)

### 4.2 Message Format (JSON over WebSocket)

#### Companion → OpenClaw

```json
// Delegate a task
{
  "type": "task_delegate",
  "taskId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "task": {
    "intent": "search_web",
    "args": {
      "query": "mini pupper ROS2 SDK documentation",
      "count": 5
    },
    "context": {
      "conversation_summary": "User wants to find SDK docs for ROS2 on Mini Pupper"
    }
  },
  "metadata": {
    "user_id": "user-1",
    "timestamp": "2026-05-09T08:33:00Z"
  }
}

// Query task status
{
  "type": "task_status_query",
  "taskId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}

// Cancel task
{
  "type": "task_cancel",
  "taskId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

#### OpenClaw → Companion

```json
// Task accepted
{
  "type": "task_status",
  "taskId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "accepted",
  "detail": "Task queued, starting execution",
  "timestamp": "2026-05-09T08:33:01Z"
}

// Progress update
{
  "type": "task_status",
  "taskId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "in_progress",
  "stage": "searching_web",
  "detail": "Searching for 'mini pupper ROS2 SDK documentation'",
  "timestamp": "2026-05-09T08:33:05Z"
}

// Tool invocation
{
  "type": "task_status",
  "taskId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "in_progress",
  "stage": "fetching_page",
  "detail": "Opening first search result...",
  "url": "https://docs.minipupper.com/ros2",
  "timestamp": "2026-05-09T08:33:08Z"
}

// Completed
{
  "type": "task_completed",
  "taskId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "result": {
    "success": true,
    "data": {
      "summary": "Mini Pupper supports ROS2 Humble natively...",
      "sources": [
        {"title": "Getting Started", "url": "https://docs.minipupper.com/ros2"},
        "..."
      ]
    }
  },
  "execution_time_ms": 12400,
  "timestamp": "2026-05-09T08:33:14Z"
}

// Failed
{
  "type": "task_failed",
  "taskId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "error": {
    "code": "TIMEOUT",
    "message": "Task exceeded 60s timeout"
  },
  "timestamp": "2026-05-09T08:34:00Z"
}
```

### 4.3 Event Throttling

To avoid flooding the TTS pipeline:
- Companion app buffers status updates for **300-500ms** before processing
- Only **narrates meaningful transitions** (not every sub-step)
- Unimportant updates are coalesced: "Looking that up… still working… almost there" → "Looking that up… almost there"

---

## 5. Data Flow — Full Conversation Example

```
User:           "Hey, can you find the latest OpenClaw release notes?"

Companion ASR:  [transcribes to text]
Companion LLM:  [classifies → delegate task]
Companion TTS:  "Let me look that up for you."                     ← immediate ack (<500ms)

Companion→OC:   task_delegate { intent: "search_web", query: "OpenClaw release notes 2026" }

OC→Companion:   task_status { status: "accepted" }
OC→Companion:   task_status { status: "in_progress", stage: "searching_web" }

Companion LLM:  [status="looking up release notes..."]
Companion TTS:  "I'm searching for the latest OpenClaw release notes now."  ← <1.5s from utterance

OC→Companion:   task_status { status: "in_progress", stage: "fetching_results" }

OC→Companion:   task_completed { result: { success: true, data: {...} } }

Companion LLM:  [summarize result into conversational text]
Companion TTS:  "Here's what I found. The latest release is v2.1.0 from April 2026..."  ← final output

User:           "Can you make the robot do a dance?"

Companion LLM:  [classifies → delegate task]
Companion TTS:  "Sure, let's get the Mini Pupper moving."

Companion→OC:   task_delegate { intent: "robot_control", args: { action: "dance" } }

OC→Companion:   task_status { status: "in_progress", stage: "activating_robot" }
OC→Companion:   task_status { status: "in_progress", stage: "executing_dance" }
OC→Companion:   task_completed { result: { success: true } }

Companion TTS:  "All done! The robot just finished its dance routine."

User:           "Great, what else can you do?"

Companion LLM:  [classifies → converse; no delegation needed]
Companion TTS:  "I can search the web, browse pages, control the Mini Pupper..."  ← fast, no OpenClaw round-trip
```

---

## 6. State & Session Management

### 6.1 Companion App State (in-memory)

```json
{
  "activeTasks": {
    "a1b2c3d4-...": {
      "taskId": "a1b2c3d4-...",
      "intent": "search_web",
      "status": "in_progress",
      "stage": "searching_web",
      "detail": "...",
      "startedAt": "2026-05-09T08:33:00Z",
      "updates": [
        { "status": "accepted", "detail": "...", "ts": "..." },
        { "status": "in_progress", "stage": "searching_web", "ts": "..." }
      ],
      "result": null
    }
  },
  "conversationHistory": [
    { "role": "user", "text": "Can you find..." },
    { "role": "assistant", "text": "Let me look that up..." },
    { "role": "system", "text": "status: searching for release notes..." }
  ],
  "ttsQueue": [],
  "wakeWordEnabled": true,
  "muted": false
}
```

### 6.2 OpenClaw — Companion Bridge

A lightweight OpenClaw plugin that:
- Accepts incoming task requests via WebSocket/REST
- Creates sub-agent sessions for each task (isolated context)
- Streams tool call logs as structured status events back to companion
- Supports cancellation (kills sub-agent)
- Optionally enforces per-user rate limits and task timeouts

---

## 7. Implementation Roadmap

### Phase 1: Local MVP (proof-of-concept)
- [ ] Companion app with Whisper (offline) + Piper TTS (offline)
- [ ] Companion LLM (Phi-4 or Llama 3.2 3B via llama.cpp)
- [ ] Simple intent router (regex + keyword → classify)
- [ ] REST API bridge to OpenClaw (`POST /api/tasks`)
- [ ] OpenClaw plugin: task listener + status reporter (webhook to companion)
- [ ] Basic user flow: "search X" → delegate → summarize result → speak

### Phase 2: Voice UX Polish
- [ ] Streaming ASR (real-time partial results)
- [ ] Interruptible TTS (new utterance cancels current speech)
- [ ] Status buffering + coalescing for natural narration
- [ ] Wake word detection (Porcupine / local Vosk)
- [ ] Push-to-talk fallback

### Phase 3: Production Protocol
- [ ] WebSocket transport (replaces REST polling)
- [ ] Full state machine (accept → in_progress → tool_invoke → partial → complete/fail)
- [ ] Parallel task support (multiple delegations in flight)
- [ ] Graceful degradation when OpenClaw is offline

### Phase 4: Advanced Features
- [ ] Voice biometrics (user identification)
- [ ] Multi-language ASR/TTS
- [ ] Companion LLM fine-tuned on user's common task patterns
- [ ] Persistent user profiles (preferences, common queries)
- [ ] Mobile companion app (phone → OpenClaw server → robot)

---

## 8. Technology Candidates

| Component | Option 1 | Option 2 | Option 3 |
|---|---|---|---|
| ASR | Whisper (faster-whisper) | Whisper.cpp | Deepgram API |
| TTS | Piper TTS | ElevenLabs API | Coqui TTS |
| Companion LLM | Llama 3.2 3B (q4) | Phi-4 | Qwen 2.5 7B |
| LLM Runtime | llama.cpp | Ollama | MLX (Apple Silicon) |
| Wake Word | Porcupine (Picovoice) | Vosk | snowboy |
| Transport | WebSocket | REST + SSE | MQTT |
| OpenClaw Plugin | Python SDK | REST API | Sub-agent interface |

---

## 9. Open Questions

1. **Delegation granularity** — Should OpenClaw receive a high-level intent and figure out the steps, or should the companion LLM plan the steps and send them individually?
   - **Recommendation:** High-level intent + optional constraints. OpenClaw's existing agent handles planning. This keeps the companion LLM thin and fast.

2. **Authentication** — How does the companion app authenticate to OpenClaw?
   - **Recommendation:** API token (same as other OpenClaw integrations). Or local-only (Unix socket) for same-machine setups.

3. **Companion LLM size vs speed tradeoff** — 3B is fast on CPU but dumber at classification. 7B is smarter but needs GPU.
   - **Recommendation:** Start with 3B + explicit regex classifier as guard. Upgrade to 7B if classification errors are too frequent.

4. **Task timeout defaults** — How long should OpenClaw run before the companion app considers it stalled?
   - **Recommendation:** Configurable per task type (search: 30s, browse: 60s, robot: 120s). Default 60s.

5. **Streaming TTS + status** — Should TTS queue flush when a major status update arrives mid-sentence?
   - **Recommendation:** Yes — major status changes (completed, failed) should bump the TTS queue. Minor updates (in_progress stages) should be buffered.

---

## 10. Appendix: OpenClaw Plugin Skeleton (Python)

```python
# openclaw_companion/plugin.py

import asyncio
import uuid
import time
from typing import Callable

class CompanionBridgePlugin:
    """OpenClaw plugin that accepts tasks from the companion app."""

    def __init__(self, status_callback: Callable):
        self.status_callback = status_callback
        self.active_tasks = {}

    async def accept_task(self, payload: dict) -> str:
        task_id = str(uuid.uuid4())
        self.active_tasks[task_id] = {
            "status": "accepted",
            "started_at": time.time()
        }
        # Emit accepted status
        await self._emit_status(task_id, "accepted", detail="Task received")
        # Launch sub-agent for execution
        asyncio.create_task(self._execute_task(task_id, payload))
        return task_id

    async def _execute_task(self, task_id: str, payload: dict):
        """Launches an OpenClaw sub-agent for the task."""
        task = payload.get("task", {})
        await self._emit_status(task_id, "in_progress",
                                detail=f"Starting task: {task.get('intent', 'unknown')}")

        # TODO: Create sub-agent session, pipe tool calls as status updates
        # Example: sessions_spawn(task=...)

        # TODO: Collect final result
        result = {"success": True, "data": "..."}
        await self._emit_completed(task_id, result)

    async def _emit_status(self, task_id: str, status: str, **kwargs):
        event = {
            "type": "task_status",
            "taskId": task_id,
            "status": status,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            **kwargs
        }
        await self.status_callback(event)

    async def cancel_task(self, task_id: str):
        if task_id in self.active_tasks:
            # Kill sub-agent
            await self._emit_status(task_id, "cancelled", detail="Cancelled by user")
            del self.active_tasks[task_id]
```

---

## 11. Next Steps

1. Decide on MVP tech stack (ASR, TTS, LLM runtime)
2. Prototype the intent classifier (regex → LLM)
3. Build the OpenClaw plugin (task listener endpoint)
4. Wire up end-to-end: user speech → ASR → classify → delegate → execute → status → TTS
5. Measure latency at each step, identify bottlenecks
6. Iterate on the communication protocol for robustness