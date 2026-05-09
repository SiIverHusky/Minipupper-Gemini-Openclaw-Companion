# Companion App — Pairing & Protocol Guide

> **How the Voice Companion App connects to OpenClaw, authenticates, delegates tasks, and receives real-time status updates.**
>
> Design doc: [`DESIGN.md`](./DESIGN.md)

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Authentication & Pairing](#2-authentication--pairing)
3. [Gateway WebSocket Protocol](#3-gateway-websocket-protocol)
4. [Task Delegation Strategies](#4-task-delegation-strategies)
5. [Receiving Status Updates](#5-receiving-status-updates)
6. [Cancellation & Interruption](#6-cancellation--interruption)
7. [Security & Permissions](#7-security--permissions)
8. [Network Topologies](#8-network-topologies)
9. [Troubleshooting](#9-troubleshooting)
10. [Reference Links](#10-reference-links)

---

## 1. Architecture Overview

The companion app communicates with OpenClaw through the **Gateway WebSocket** — the same control plane used by the CLI, web UI, and macOS/iOS/Android apps. There is no separate "companion API"; the Gateway WS is the single integration surface for everything.

```
┌─────────────────────┐          WS                   ┌─────────────────────────┐
│ Companion App        │ ◄══════════════════════►      │ OpenClaw Gateway         │
│                     │     ws://host:18789           │                         │
│  ┌───────────────┐  │     role: "operator"          │  ┌───────────────────┐  │
│  │ WS Client     │──┼───────────────────────────────┼─►│  Agent Runtime     │  │
│  │ (Gateway      │  │                               │  │  (sessions.send)   │  │
│  │  Protocol v3) │  │                               │  └───────────────────┘  │
│  └───────────────┘  │                               │  ┌───────────────────┐  │
│  ┌───────────────┐  │     task_status events        │  │  Sub-agent Mgmt   │  │
│  │ Status Buffer  │◄─┼──────────────────────────────┼──│  (sessions_spawn) │  │
│  │ (coalesces     │  │                               │  └───────────────────┘  │
│  │  raw status    │  │                               │  ┌───────────────────┐  │
│  │  → TTS-ready)  │  │                               │  │  Tasks Registry   │  │
│  └───────────────┘  │                               │  │  (background      │  │
│                     │                               │  │   task tracking)  │  │
└─────────────────────┘                               │  └───────────────────┘  │
                                                      │                         │
                                                      │  ┌───────────────────┐  │
                                                      │  │  Subscribable     │  │
                                                      │  │  Events (session  │  │
                                                      │  │  messages, task   │  │
                                                      │  │  status, etc.)    │  │
                                                      │  └───────────────────┘  │
                                                      └─────────────────────────┘
```

**Key insight:** the companion app connects as an `operator`-role WebSocket client, exactly like the CLI or Control UI. It can:
- Send messages to agent sessions (`sessions.send`, `chat.send`)
- Spawn sub-agents for isolated task execution
- Subscribe to session message events for real-time streaming
- Query and manage the background tasks registry
- Control cron, nodes, and other Gateway features

---

## 2. Authentication & Pairing

### 2.1 Finding Your Gateway Auth Token

The Gateway is configured with an auth mechanism. There are several ways to authenticate:

**Option A: Shared token (most common)**

If you ran `openclaw setup` or `openclaw onboard`, a token was generated:

```bash
# Read the current auth token
openclaw config get gateway.auth.token
# Or check the auto-generated token path
cat ~/.openclaw/gateway.token  # may exist
```

**Option B: Set a custom token**

```bash
openclaw config set gateway.auth.mode "token"
openclaw config set gateway.auth.token "my-companion-secret"
```

Then restart the Gateway.

**Option C: Password mode**

```bash
openclaw config set gateway.auth.mode "password"
openclaw config set gateway.auth.password "my-password"
```

> **See:** [Gateway configuration — `gateway.auth`](/gateway/configuration)
> **Security:** [Gateway security overview](/gateway/security)

### 2.2 Connection Handshake (New Device)

Every WS client goes through a challenge-response handshake before it can send method calls.

**Step 1:** Open WebSocket to:

```
ws://127.0.0.1:18789    (local, same host)
wss://gateway-host:18789 (remote, TLS)
```

**Step 2:** Wait for the `connect.challenge` event:

```json
{
  "type": "event",
  "event": "connect.challenge",
  "payload": {
    "nonce": "abc123...",
    "ts": 1700000000000
  }
}
```

**Step 3:** Send a `connect` request with your credentials and a device identity. The device identity must include a signature over the nonce.

```json
{
  "type": "req",
  "id": "connect-1",
  "method": "connect",
  "params": {
    "minProtocol": 3,
    "maxProtocol": 3,
    "client": {
      "id": "companion-app",
      "version": "1.0.0",
      "platform": "linux",
      "mode": "operator"
    },
    "role": "operator",
    "scopes": [
      "operator.read",
      "operator.write",
      "operator.pairing"
    ],
    "caps": [],
    "commands": [],
    "permissions": {},
    "auth": {
      "token": "my-companion-secret"
    },
    "locale": "en-US",
    "userAgent": "openclaw-companion/1.0.0",
    "device": {
      "id": "companion_device_fingerprint",
      "publicKey": "<base64-encoded-public-key>",
      "signature": "<signature-over-nonce>",
      "signedAt": 1700000000000,
      "nonce": "abc123..."
    }
  }
}
```

**Step 4:** On success, Gateway responds with `hello-ok`:

```json
{
  "type": "res",
  "id": "connect-1",
  "ok": true,
  "payload": {
    "type": "hello-ok",
    "protocol": 3,
    "server": { "version": "2026.4.28", "connId": "..." },
    "features": {
      "methods": ["sessions.send", "sessions.subscribe", "tools.invoke", "..."],
      "events": ["session.message", "session.tool", "presence", "..."]
    },
    "auth": {
      "role": "operator",
      "scopes": ["operator.read", "operator.write", "operator.pairing"],
      "deviceToken": "issued-device-token..."
    },
    "policy": {
      "maxPayload": 26214400,
      "maxBufferedBytes": 52428800,
      "tickIntervalMs": 15000
    }
  }
}
```

> **Full protocol docs:** [Gateway protocol](/gateway/protocol)
> **Device identity spec:** `device.id`, `device.publicKey`, `device.signature`, `device.signedAt`, `device.nonce` — all required

### 2.3 Device Pairing (First Connect)

On first connect from an unknown device, the Gateway may respond with a pairing error:

```json
{
  "type": "res",
  "id": "connect-1",
  "ok": false,
  "error": {
    "code": "DEVICE_PAIRING_REQUIRED",
    "details": { "requestId": "pair-xxx" }
  }
}
```

**To approve the pairing:**

```bash
# List pending pairing requests
openclaw devices list

# Approve by request ID
openclaw devices approve pair-xxx
```

**Auto-approval shortcut:** If the companion app runs on the same machine as the Gateway (loopback `127.0.0.1`), local auto-approval may be enabled. Otherwise, you must approve explicitly.

> **See:** [Control UI pairing](/web/control-ui#device-pairing-first-connection)
> **Devices CLI:** [Device pairing + token rotation](/cli/devices)

### 2.4 Reconnecting with a Stored Device Token

After successful pairing, persist the `deviceToken` from `hello-ok.auth.deviceToken` and use it on reconnection:

```json
{
  "type": "req",
  "id": "connect-2",
  "method": "connect",
  "params": {
    "minProtocol": 3,
    "maxProtocol": 3,
    "client": { "id": "companion-app", "version": "1.0.0", "platform": "linux", "mode": "operator" },
    "role": "operator",
    "scopes": ["operator.read", "operator.write", "operator.pairing"],
    "auth": { "token": "<stored-device-token>" },
    "device": {
      "id": "companion_device_fingerprint",
      "publicKey": "<same-public-key>",
      "signature": "<new-signature>",
      "signedAt": 1700000000000,
      "nonce": "<new-nonce>"
    }
  }
}
```

**Important:** The stored device token preserves the approved scope set; reconnections don't lose access.

> **See:** [Gateway protocol — Auth](/gateway/protocol#auth)

### 2.5 Simple Fallback: ACP Bridge (stdio → WS)

If implementing the full Gateway WS protocol is too heavy for an MVP, the companion app can spawn the ACP bridge:

```bash
openclaw acp --session agent:main:main
```

This runs a stdio-based ACP server that translates ACP calls into Gateway WS calls. Your companion app writes ACP requests to stdin and reads responses from stdout.

For the MVP, this lets you avoid implementing the handshake, challenge-response, and device identity logic.

> **See:** [ACP CLI](/cli/acp)

---

## 3. Gateway WebSocket Protocol

### 3.1 Connection Lifecycle

```
Client                     Gateway
  │                          │
  │──── WebSocket open ────►│
  │                          │
  │◄── connect.challenge ───│    (server nonce)
  │                          │
  │──── connect (signed) ──►│
  │                          │
  │◄── hello-ok ────────────│    (device token, features, policy)
  │                          │
  │──── RPC requests ──────►│    (sessions.send, tools.invoke, etc.)
  │                          │
  │◄── RPC responses ──────│
  │◄── broadcast events ───│    (session.message, session.tool, presence)
  │                          │
  │──── disconnect ────────►│
```

### 3.2 Framing

All messages are **JSON text frames** over WebSocket.

| Frame type | Direction      | Format |
|-----------|----------------|--------|
| Request   | Client → Server | `{"type":"req","id":"<unique>","method":"<method>","params":{...}}` |
| Response  | Server → Client | `{"type":"res","id":"<match>","ok":true,"payload":{...}}` or `{"type":"res","id":"<match>","ok":false,"error":{...}}` |
| Event     | Server → Client | `{"type":"event","event":"<event-name>","payload":{...},"seq":<n>}` |

> **See:** [Gateway protocol — Framing](/gateway/protocol#framing)

### 3.3 Tick / Keepalive

The Gateway sends periodic `tick` events. If no data arrives within `tickIntervalMs * 2` (default: 30s), the Gateway may close the connection.

The companion app should:
- Respond to ticks by resetting its own keepalive timer
- Send a minimal RPC if idle to prevent timeout (or rely on the tick interval)

---

## 4. Task Delegation Strategies

There are **three approaches** for delegating tasks to OpenClaw. Choose based on your latency and complexity requirements.

### 4.1 Strategy A: Direct Session Send (Simplest)

Send a message into an existing **main session** and subscribe to message events to get the response.

**Best for:** MVP, when the companion app is the only client and doesn't need task isolation.

**How it works:**

```json
// 1. Subscribe to session messages
{
  "type": "req",
  "id": "sub-1",
  "method": "sessions.messages.subscribe",
  "params": { "sessionKey": "agent:main:main" }
}

// 2. Send the task as a user message
{
  "type": "req",
  "id": "send-1",
  "method": "sessions.send",
  "params": {
    "key": "agent:main:main",
    "message": "Search the web for OpenClaw release notes 2026. Return raw results, don't summarize."
  }
}
```

**Receiving the response:**

Subscribe to `session.message` events emitted by the Gateway:

```json
{
  "type": "event",
  "event": "session.message",
  "payload": {
    "sessionKey": "agent:main:main",
    "message": {
      "role": "assistant",
      "text": "Here are the results I found...",
      "seq": 5
    }
  },
  "seq": 42
}
```

You can also subscribe to `session.tool` events to see tool invocations as they happen:

```json
{
  "type": "event",
  "event": "session.tool",
  "payload": {
    "sessionKey": "agent:main:main",
    "toolName": "web_search",
    "args": { "query": "OpenClaw release notes 2026" },
    "result": { "...": "..." }
  },
  "seq": 43
}
```

> **RPC methods:** `sessions.send`, `sessions.subscribe`, `sessions.messages.subscribe`, `sessions.unsubscribe`, `sessions.messages.unsubscribe`
> **See:** [Gateway protocol — Agent and session helpers](/gateway/protocol#agent-and-workspace-helpers)

**Pros:** Simplest to implement.
**Cons:** No task isolation; couples companion state with main session. No per-task status tracking.

### 4.2 Strategy B: Sub-Agent per Task (Recommended)

Spawn an isolated sub-agent session for each task. This gives you isolated execution, per-task status via the background tasks system, and clean cancellation.

**Best for:** Production use where multiple tasks can run concurrently, each requiring isolation.

**How it works:**

The companion app sends a message to a **dedicated task delegation session** that spawns a sub-agent:

```python
# Companion app sends to the orchestration session:
{
  "type": "req",
  "id": "send-1",
  "method": "sessions.send",
  "params": {
    "key": "agent:main:companion",
    "message": json.dumps({
      "type": "task_request",
      "taskId": "a1b2c3d4-...",
      "intent": "search_web",
      "args": { "query": "OpenClaw release notes 2026" }
    })
  }
}
```

Inside OpenClaw, the agent in the `companion` session (configured via hooks/standing orders) recognizes the structured request and spawns a sub-agent:

```
sessions_spawn(
    task="Search the web for OpenClaw release notes 2026. "
         "Your task ID is a1b2c3d4-.... "
         "Report progress via the companion status channel.",
    context="isolated"
)
```

> **See:** Sub-agent spawning via the `sessions_spawn` tool
> **OpenClaw skill reference:** [taskflow](/automation/taskflow)

**Tracking task status:**

When a sub-agent is spawned, a **background task record** is created. The companion app can:

1. **Query tasks directly** via the Gateway protocol (if `tasks.*` methods exist) or CLI
2. **Listen for task completion notifications** — completions trigger heartbeat wakes
3. **Check via `sessions.preview`** on the sub-agent session key

```
openclaw tasks list --status running
openclaw tasks show <task-id>
```

> **See:** [Background tasks](/automation/tasks) — task lifecycle, delivery, notify policies

### 4.3 Strategy C: Cron Job Delegation (Isolated & Scheduled)

Use cron jobs for tasks that should run with complete isolation and deliver results to a channel or webhook.

**Best for:** Scheduled/recurring tasks, or when the companion app wants webhook delivery.

```bash
openclaw cron add \
  --name "Companion Task" \
  --at "now" \
  --delete-after-run \
  --message "Search the web for OpenClaw release notes 2026" \
  --delivery webhook \
  --delivery-to "http://companion-app:8080/webhook/task-result"
```

Or via the Gateway protocol:

```json
{
  "type": "req",
  "id": "cron-1",
  "method": "cron.add",
  "params": {
    "name": "Companion Task",
    "schedule": { "kind": "at", "at": "2026-05-09T08:35:00Z" },
    "payload": {
      "kind": "agentTurn",
      "message": "Search the web for OpenClaw release notes 2026"
    },
    "delivery": {
      "mode": "webhook",
      "to": "http://companion-app:8080/webhook/task-result"
    },
    "deleteAfterRun": true
  }
}
```

> **See:** [Scheduled tasks (Cron)](/automation/cron-jobs) — schedule types, webhook delivery
> **Cron CLI:** [`openclaw cron add`](/cli/cron)

---

## 5. Receiving Status Updates

### 5.1 Option A: Session Message Events (Real-Time)

This is the **primary approach** for real-time streaming. The companion app subscribes to session message events and receives tool calls, assistant replies, and system notices as they happen.

**Subscription flow:**

```json
// 1. Subscribe to session metadata changes (optional — get notified of new sessions)
{ "type": "req", "id": "sub1", "method": "sessions.subscribe", "params": {} }

// 2. Subscribe to message events for a specific session
{ "type": "req", "id": "sub2", "method": "sessions.messages.subscribe",
  "params": { "sessionKey": "agent:main:main" } }
```

**Events you receive:**

```json
// Tool call started (companion can announce: "searching the web...")
{
  "type": "event",
  "event": "session.tool",
  "payload": {
    "sessionKey": "agent:main:main",
    "toolName": "web_search",
    "args": { "query": "..." },
    "status": "started"
  },
  "seq": 50
}

// Tool call completed
{
  "type": "event",
  "event": "session.tool",
  "payload": {
    "sessionKey": "agent:main:main",
    "toolName": "web_search",
    "result": { "success": true, "data": [...] }
  },
  "seq": 51
}

// Assistant started replying
{
  "type": "event",
  "event": "session.message",
  "payload": {
    "sessionKey": "agent:main:main",
    "message": { "role": "assistant", "partial": true },
    "seq": 52
  }
}

// Final assistant reply
{
  "type": "event",
  "event": "session.message",
  "payload": {
    "sessionKey": "agent:main:main",
    "message": { "role": "assistant", "text": "Full result here..." }
  },
  "seq": 53
}
```

> **See:** [Gateway protocol — Common event families](/gateway/protocol#common-event-families)

### 5.2 Option B: Task Status via CLI/Tasks API

For background tasks (subagents, cron), the companion app can poll the tasks registry:

```bash
openclaw tasks list --status running --json
openclaw tasks show <task-id> --json
```

Or via the Gateway protocol (if the Gateway exposes a `tasks.*` method — check `hello-ok.features.methods`).

### 5.3 Option C: Notification Policies

When using sub-agents (Strategy B), you can set the **notification policy** to `state_changes` to get granular updates delivered to the requester session:

```bash
openclaw tasks notify <task-id> state_changes
```

This causes every state transition (`queued → running → succeeded/failed`) to generate a delivery notification.

> **See:** [Background tasks — Notification policies](/automation/tasks#notification-policies)

### 5.4 Best Practice: Buffering & Coalescing

Raw status events are **too granular** for TTS narration. The companion app should:

1. **Buffer events** for 300-500ms
2. **Coalesce** minor updates (three `in_progress` phases → one announcement)
3. **Narrate meaningful transitions only:**
   - `accepted` → "Looking that up..."
   - `in_progress` → (only narrate if it takes >2s) "Still working..."
   - `completed` → (use LLM to summarize)
   - `failed` → "I ran into an issue..."

```
Raw events:          accepted → in_progress → tool:search → tool:fetch → completed
Coalesced events:    [accepted] → [tool:search] → [completed]
TTS output:          "Looking that up..." → (silence, 500ms) → "Found it. The latest release..."
```

---

## 6. Cancellation & Interruption

The companion app can abort active work in several ways:

### 6.1 Abort a Session Run

```json
{
  "type": "req",
  "id": "abort-1",
  "method": "sessions.abort",
  "params": { "key": "agent:main:main" }
}
```

This stops the currently executing agent turn for that session.

> **See:** [Gateway protocol — Session control](/gateway/protocol#session-control)

### 6.2 Cancel a Background Task

```bash
openclaw tasks cancel <task-id>
```

Or via the Gateway protocol (if `tasks.cancel` method is available).

### 6.3 Interrupt via Companion LLM Routing

When the user says "stop" or "cancel", the companion app's intent router should:

1. Call `sessions.abort` on the active session
2. Clear the TTS queue
3. Respond with "Stopped. What would you like instead?"

---

## 7. Security & Permissions

### 7.1 Minimum Required Scopes

The companion app needs these scopes at minimum:

| Scope | Needed For |
|-------|-----------|
| `operator.read` | Reading session state, subscribing to events |
| `operator.write` | Sending messages (`sessions.send`) |
| `operator.pairing` | If it needs to pair devices or manage node pairing |

> **See:** [Gateway protocol — Roles + scopes](/gateway/protocol#roles--scopes)
> **Full reference:** [Operator scopes](/gateway/operator-scopes)

### 7.2 Token Security

- **Never** hardcode tokens in the companion app source
- Prefer `--token-file` or environment variables (`OPENCLAW_GATEWAY_TOKEN`)
- Store the device token securely (OS keychain, encrypted config file)
- Rotate tokens periodically via `openclaw devices rotate`

### 7.3 Local vs Remote Connections

| Connection type | Security |
|----------------|---------|
| Same-host (ws://127.0.0.1:18789) | Auto-approved pairing, no TLS needed |
| Tailscale (wss://tailscale-host) | TLS via Tailscale, pairing required |
| LAN (ws://192.168.x.x) | No TLS, pairing required. **Not recommended** over untrusted networks |
| Public internet (wss://) | TLS required, pairing required, use firewall |

> **See:** [Network architecture](/network)

---

## 8. Network Topologies

### 8.1 Same Machine (Simplest)

```
Companion App ──ws://127.0.0.1:18789──► Gateway (same host)
```

- No TLS needed
- Auto-approval of device pairing
- Lowest latency

### 8.2 Tailscale (Split Machine)

```
Companion App ──wss://tailscale-host:18789──► Gateway
```

Recommended for:
- Companion app on a different device (e.g., a phone running a local TTS)
- Encrypted tunnel via Tailscale mesh
- Requires explicit pairing approval

> **Remote access via Tailscale:** See [/gateway/tailscale](/gateway/tailscale)
> **Remote access via SSH tunnel:** See [/gateway/remote](/gateway/remote)

### 8.3 Companion App as a Node (Alternative Architecture)

An advanced alternative: the companion app connects as a **node** (not an operator), exposing ASR/TTS capabilities as node commands. The Gateway can then invoke `companion.speak` or `companion.listen` as tool calls. This reverses the control flow:

```
OpenClaw Agent ──node.invoke──► Companion App (as node)
                                └── TTS pipeline
```

> **See:** [Nodes overview](/nodes)
> **Node pairing:** [Gateway-owned pairing](/gateway/pairing)

---

## 9. Troubleshooting

### "Connection refused" (ECONNREFUSED)
```
Gateway not running. Start it:
openclaw gateway
```

### "disconnected (1008): pairing required"
```
New device needs approval:
openclaw devices list
openclaw devices approve <requestId>
```

### "disconnected (1008): auth token mismatch"
```
Token is invalid or expired. Generate a new one:
openclaw config get gateway.auth.token
# Or set a new one:
openclaw config set gateway.auth.token "new-token"
```

### No message events arriving
```
Check you subscribed correctly:
sessions.messages.subscribe { "sessionKey": "agent:main:main" }

The session key must match exactly.
List available sessions:
openclaw sessions --json
```

### Sub-agent tasks not creating task records
```
Sub-agent tasks (sessions_spawn) always create task records.
Check:
openclaw tasks list --runtime subagent
openclaw tasks audit
```

> **See:** [Gateway troubleshooting](/gateway/troubleshooting)
> **Doctor tool:** `openclaw doctor`

---

## 10. Reference Links

### Official OpenClaw Documentation

| Document | Link |
|----------|------|
| Gateway WebSocket Protocol | [`docs/gateway/protocol.md`](/gateway/protocol) |
| Gateway Configuration | [`docs/gateway/configuration.md`](/gateway/configuration) |
| Network Architecture | [`docs/network.md`](/network) |
| Nodes Overview | [`docs/nodes/index.md`](/nodes) |
| Background Tasks | [`docs/automation/tasks.md`](/automation/tasks) |
| Scheduled Tasks (Cron) | [`docs/automation/cron-jobs.md`](/automation/cron-jobs) |
| Gateway-owned Pairing | [`docs/gateway/pairing.md`](/gateway/pairing) |
| Talk Mode (TTS) | [`docs/nodes/talk.md`](/nodes/talk) |
| Session Management | [`docs/concepts/session.md`](/concepts/session) |
| Control UI | [`docs/web/control-ui.md`](/web/control-ui) |
| ACP Bridge | [`docs/cli/acp.md`](/cli/acp) |
| Automation Overview | [`docs/automation/index.md`](/automation) |
| Task Flow | [`docs/automation/taskflow.md`](/automation/taskflow) |
| Devices CLI | [`docs/cli/devices.md`](/cli/devices) |
| Operator Scopes | [`docs/gateway/operator-scopes.md`](/gateway/operator-scopes) |
| Remote Access | [`docs/gateway/remote.md`](/gateway/remote) |
| Tailscale | [`docs/gateway/tailscale.md`](/gateway/tailscale) |

### Source Code Reference (for protocol schema)

- Protocol schema: `src/gateway/protocol/schema/frames.ts`
- Client implementation: `src/gateway/client.ts`
- Server methods: `src/gateway/server-methods-list.ts`

---

## Appendix: Quick Reference Card

### Gateway WS Endpoint
```
Local:  ws://127.0.0.1:18789
Remote: wss://<host>:18789
```

### Required Handshake Steps
1. Wait for `connect.challenge`
2. Sign the challenge nonce with your device keypair
3. Send `connect` with `auth.token` + `device` block
4. Receive `hello-ok` with `deviceToken`
5. Persist `deviceToken` for reconnection

### Essential RPC Methods for Companion App

| Method | Purpose |
|--------|---------|
| `sessions.send` | Send a task into a session |
| `sessions.subscribe` | Subscribe to session list changes |
| `sessions.messages.subscribe` | Subscribe to message events for real-time streaming |
| `sessions.abort` | Cancel active work in a session |
| `sessions.preview` | Read recent transcript lines |
| `sessions.list` | List available sessions |
| `cron.add` | Create a detached cron task |
| `cron.list` | List cron jobs |
| `talk.speak` | Speak text through Gateway's TTS |
| `tts.convert` | Convert text to speech audio |

### Noteworthy Events

| Event | Purpose |
|-------|---------|
| `session.message` | New assistant/user message |
| `session.tool` | Tool invocation result |
| `sessions.changed` | Session index changed |
| `tick` | Keepalive |

### MVP Recommendation

For the fastest path to a working prototype:

1. Use **ACP bridge** (`openclaw acp`) to avoid implementing the WS handshake
2. Use **Strategy A** (direct `sessions.send` to main session)
3. Subscribe to `session.message` events for real-time streaming
4. Buffer and coalesce events before TTS
5. Add sub-agent isolation (Strategy B) in Phase 2