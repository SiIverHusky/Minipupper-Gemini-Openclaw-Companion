# Phase 2 - OpenClaw Agent Integration Protocol

**Protocol Version:** minipupper-v1  
**Last Updated:** 2026-05-11

## Overview

Phase 2 connects the Minipupper Operator app's Gemini LLM to the OpenClaw
agent for complex task offloading. Gemini decides which tasks need the agent's
tool use / reasoning capabilities, formats them as structured protocol messages,
and the agent handles execution with regular status updates.

## Architecture

```
User speaks → ASR → Gemini LLM
  ├─ Simple requests → handle locally
  └─ Complex tasks → format as protocol message
                     → send to OpenClaw agent (main session)
                     → agent works on task
                     → periodic status updates → TTS announcement
                     → final result → TTS completion
```

## Communication Protocol

All messages are JSON strings with `"protocol": "minipupper-v1"`.

### App → Agent (Task Request)

Sent via `gateway_client.send_sessions_send("main", json_string)`:

```json
{
  "protocol": "minipupper-v1",
  "type": "task",
  "taskId": "uuid-or-short-id",
  "action": "task_name",
  "params": { ... },
  "userQuery": "original user request from ASR",
  "timestamp": 1746946000
}
```

### Agent → App (Status Update)

Received as `session.message` with `role: assistant` in the main session:

```json
{
  "protocol": "minipupper-v1",
  "type": "status",
  "taskId": "abc123",
  "phase": "analyzing",
  "progress": 42.0,
  "message": "Analyzing the code structure...",
  "timestamp": 1746946000
}
```

### Agent → App (Task Result)

```json
{
  "protocol": "minipupper-v1",
  "type": "result",
  "taskId": "abc123",
  "status": "completed",
  "result": "The analysis shows...",
  "error": null,
  "timestamp": 1746946000
}
```

On failure: `"status": "failed"` with `"error": "error message"`.

### App → Agent (On-demand Progress Query)

```json
{
  "protocol": "minipupper-v1",
  "type": "status_query",
  "taskId": "abc123",
  "timestamp": 1746946000
}
```

## App-Side Changes (Done)

- **`protocol.py`** — Message type dataclasses and parsers
- **`src/core/protocol_handler.py`** — Parses protocol frames, extracts
  structured status/result, generates LLM announcement prompt
- **`minipupper_operator.py`** — `_handle_openclaw_frame` updated to
  check for protocol messages first (fast-path), falls back to legacy parsing

## Agent Response Format

When I (the agent) reply in the main session during task work, my messages
are structured JSON. The app's protocol_handler parses these and generates
a natural TTS announcement via Gemini.

## Task Lifecycle

1. Gemini sends `type: "task"` with a taskId
2. Agent creates task entry in tracker (~/.openclaw/workspace/minipupper/tasks.json)
3. Agent replies with `type: "status"` updates as work progresses
4. Agent sends `type: "result"` when complete
5. App announces completion via TTS

## Agent Capabilities (available actions)

| Action | Description |
|--------|-------------|
| `research` | Web search / fetch / analyze |
| `code_analysis` | Read, analyze, modify code |
| `file_operations` | Read/write/manage files on the Pi |
| `robot_control` | Send movement commands to Mini Pupper |
| `system_admin` | Check logs, processes, system status |
| `custom` | Free-form task with params |

Actions can be extended as needed — just define the action name and params,
and the agent will interpret them.
