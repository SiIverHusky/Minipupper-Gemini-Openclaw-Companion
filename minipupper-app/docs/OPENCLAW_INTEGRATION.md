# OpenClaw Gateway Integration — Minipupper App

**Status:** Design Document  
**Last Updated:** 2026-05-10  
**Target:** Connect `minipupper-app` (voice/speech frontend) to the OpenClaw Gateway (agent session)

---

## 1. Architecture Overview

The system has two machines on a shared Tailscale network:

- **Cloud server** `your-gateway-hostname.ts.net` — runs the OpenClaw Gateway (port 443, TLS)
- **Raspberry Pi** (`minipupperv2`) — runs the node service + `minipupper-app` voice frontend

```
                              Tailscale Network
                        ┌────────────────────────┐
                        │  tail2df607.ts.net      │
                        └────────────────────────┘
                              │           │
                              │           │
         ┌────────────────────┘           └────────────────────┐
         ▼                                                      ▼
┌──────────────────────────┐                    ┌──────────────────────────┐
│   Cloud Server            │                    │   Raspberry Pi            │
│                           │                    │   (minipupperv2)          │
│  OpenClaw Gateway         │                    │                           │
│  wss://...:443 (TLS)      │◀──────────────────▶│  openclaw node run       │
│  ┌───────────────────┐    │   Tailscale TLS     │  (connected as node)     │
│  │ Agent Session     │    │                     │                           │
│  │ (main)            │    │                     │  minipupper-app           │
│  └───────────────────┘    │                    │  (voice frontend)         │
│                           │                    │  ┌─────────────────────┐  │
│                           │                    │  │ ASR (mic → text)    │  │
│                           │                    │  │ TTS (text → audio)  │  │
│                           │                    │  │ Barge-in detect     │  │
│                           │                    │  │ Checkpoint cache    │  │
│                           │                    │  │ WS operator client  │──┼──wss://...:443
│                           │                    │  └─────────────────────┘  │
└──────────────────────────┘                    └──────────────────────────┘
```

**Key principle:** The Gateway runs in the cloud. The Pi connects as both a **node**
(for robot control, system.exec, camera) and an **operator** (via the app, for
voice conversation). The app connects to the remote Gateway over a Tailscale
TLS WebSocket — the same endpoint the `openclaw node run` CLI uses.

---

## 2. Connection Protocol

The app connects to the **remote** Gateway over a **Tailscale TLS WebSocket** at
`wss://your-gateway-hostname.ts.net:443` using the
[Gateway Protocol](/gateway/protocol).

### 2.1 Why Tailscale

| Aspect | Benefit |
|--------|---------|
| **Encryption** | All traffic is encrypted in transit via WireGuard + TLS |
| **Auth** | Tailscale handles machine identity; the Gateway trusts connections within the tailnet |
| **No open ports** | The Gateway only binds to the Tailscale IP, not the public internet |
| **Same machine identity** | The Pi's Tailscale identity is stable, even if the local IP changes |

### 2.2 Device Identity & Keypair

Unlike the loopback case (shared password), a remote TLS connection requires a
**device identity** with keypair-based signing. The app needs its own
persistent keypair (or can reuse the one from the Pi's existing OpenClaw
node setup at `~/.openclaw/`).

**Key files on the Pi:**

```
~/.openclaw/
├── device-identity.json      # Device fingerprint + public key
├── device-private.pem        # Device private key (keep secret)
└── openclaw.json             # Gateway URL + paired tokens
```

If the Pi already ran `openclaw node run`, these exist from node pairing.
The app can read them to derive its own identity for the operator connection.

Alternatively, the app generates its own device identity on first run:

```bash
# The app can generate an identity keypair
openssl genpkey -algorithm ed25519 -out ~/.openclaw/minipupper-app-key.pem
openssl pkey -in ~/.openclaw/minipupper-app-key.pem -pubout
```

### 2.3 Auth Strategy

The app connects as an **operator** client. Because it's a remote connection
(not loopback), it must:
1. Wait for the `connect.challenge` from the Gateway
2. Sign the challenge with its device private key
3. Include the signed nonce + device identity in the connect request
4. Receive a `hello-ok` with a device token (on success) or a pairing-required error

**First-run pairing flow:**

```
[app]                              [Gateway]
  │                                    │
  ├── connect(challenge_nonce) ───────▶│
  │                                    ├── No token found → NOT_PAIRED
  │◀── error: NOT_PAIRED ─────────────┤
  │                                    │
  ├── pair-request ──────────────────▶│
  │                                    ├── Pending approval...
  │                                    │   (User approves via openclaw pair approve)
  │◀── pair-ok + device_token ────────┤
  │                                    │
  ├── connect(signed_nonce + token)──▶│
  │◀── hello-ok ──────────────────────┤
```

Once paired, subsequent connections include the stored device token and skip
pairing.

### 2.4 Connect Handshake (Paired)

```python
import json
import ssl
from websocket import create_connection

GATEWAY_URL = "wss://your-gateway-hostname.ts.net:443"
GATEWAY_HOST = "your-gateway-hostname.ts.net"

async def connect(device_id: str, device_key, stored_token: str) -> WebSocket:
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = True
    ssl_ctx.verify_mode = ssl.CERT_REQUIRED

    ws = create_connection(
        GATEWAY_URL,
        ssl=ssl_ctx,
        timeout=30,
        header={"Host": GATEWAY_HOST}
    )

    # 1. Receive connect.challenge
    frame = json.loads(ws.recv())
    assert frame["event"] == "connect.challenge"
    nonce = frame["payload"]["nonce"]
    ts = frame["payload"]["ts"]

    # 2. Build signature payload (v3 format recommended)
    #    The v3 payload binds: platform, deviceFamily, client info,
    #    role, scopes, token, nonce, and the server-provided ts
    payload = {
        "platform": "linux",
        "deviceFamily": "pi",
        "clientId": "minipupper-app",
        "clientVersion": "0.1.0",
        "role": "operator",
        "scopes": ["operator.read", "operator.write"],
        "token": stored_token,
        "nonce": nonce,
        "ts": ts,
    }
    signature = device_key.sign(json.dumps(payload, separators=(",",".")).encode())

    # 3. Send connect request with device identity + signature
    ws.send(json.dumps({
        "type": "req",
        "id": "conn-1",
        "method": "connect",
        "params": {
            "minProtocol": 3,
            "maxProtocol": 3,
            "client": {
                "id": "minipupper-app",
                "version": "0.1.0",
                "platform": "linux",
                "mode": "operator"
            },
            "role": "operator",
            "scopes": ["operator.read", "operator.write"],
            "caps": [],
            "commands": [],
            "permissions": {},
            "auth": {"token": stored_token},
            "locale": "en-US",
            "userAgent": "minipupper-app/0.1.0",
            "device": {
                "id": device_id,
                "publicKey": device_key.public_key_bytes(),
                "signature": signature,
                "signedAt": ts,
                "nonce": nonce,
            }
        }
    }))

    # 4. Confirm handshake
    hello = json.loads(ws.recv())
    assert hello["ok"] is True
    # hello["payload"]["auth"]["deviceToken"] may have an updated token
    return ws, hello
```

### 2.5 Reconnection

The Gateway or Tailscale connection may drop:

- **Exponential backoff** (1s, 2s, 4s, max 30s)
- On reconnect: use the **stored device token** (no re-pairing needed unless token is revoked)
- If `AUTH_TOKEN_MISMATCH` is returned: re-run pairing flow (token may have expired)

---

## 3. Conversation Flow Protocol

### 3.1 Sending Speech to the Agent

When the user speaks and ASR produces a transcript, the app sends it using
`sessions.send` to the agent's **main session**:

```json
{
  "type": "req",
  "id": "msg-172839",
  "method": "sessions.send",
  "params": {
    "sessionKey": "main",
    "message": "Stand up and look around"
  }
}
```

**Design notes:**
- `sessionKey: "main"` — targets the default agent session (same one the user
  reaches via WebChat or any other channel)
- The message holds the raw ASR transcript text

### 3.2 Receiving Responses

Subscribe to session messages after connecting:

```json
{
  "type": "req",
  "id": "sub-1",
  "method": "sessions.messages.subscribe",
  "params": {
    "sessionKey": "main"
  }
}
```

The Gateway pushes `session.message` events:

```json
{
  "type": "event",
  "event": "session.message",
  "payload": {
    "sessionKey": "main",
    "message": {
      "role": "assistant",
      "content": "I'll stand up and look around now."
    }
  }
}
```

**How the app consumes responses:**
1. `session.message` with `role: "assistant"` arrives
2. Extract `content` — this is the text to speak
3. Feed to TTS engine with barge-in support
4. While TTS plays, barge-in detector is active
5. If barge-in detected → see Section 3.4

### 3.3 Full Audio Pipeline (Tailscale)

```
[User]                    [Pi: minipupper-app]              [Cloud: Gateway]
  │                            │                                  │
  │  "Stand up"                │                                  │
  ├───────────────────────────▶│  Mic + ASR transcribe            │
  │                            │                                  │
  │                            ├── wss://...:443 ────────────────▶│  sessions.send
  │                            │  (Tailscale TLS)                 │  "Stand up"
  │                            │                                  │
  │                            │                                  ├── agent processes
  │                            │                                  │
  │                            │◀── session.message ─────────────┤
  │                            │  (Tailscale TLS)                 │
  │                            │                                  │
  │                            ├── TTS speaks response            │
  │◀───────────────────────────┤  "I'll stand up..."              │
  │                            │                                  │
  │  [hears reply]             │                                  │
```

### 3.4 Barge-in During Active Agent Response

When barge-in fires during TTS:

1. **Stop TTS playback immediately** (already implemented in audio_manager.py)
2. **Capture the interrupt speech** via mic + ASR
3. **Send new transcript** to Gateway via `sessions.send`
4. The agent's current run will see the new input as the next message in the
   conversation — no explicit steer needed unless the old response is still
   streaming. If steering is desired:

```json
{
  "type": "req",
  "id": "steer-1",
  "method": "sessions.steer",
  "params": {
    "key": "main",
    "message": "[interrupted — user said: move left instead]"
  }
}
```

---

## 4. Checkpoints & Status Reporting

### 4.1 What Are Checkpoints

A **checkpoint** is a local snapshot of the system state. The app uses it to:
- Tell the user what's happening ("One moment...", "Still thinking...")
- Recover after a crash or Gateway disconnect
- Suppress duplicate status announcements
- **Become connectivity-aware** — if Tailscale or the Gateway drops, the
  checkpoint records the last known state so recovery knows what was lost

### 4.2 State Machine

```
 IDLE
  │
 LISTENING ──(VAD)──▶ RECORDING ──(ASR)──▶ SENDING_TO_AGENT
  │                                               │
  │                                               ▼
  │                                         AWAITING_REPLY ──(timeout)──▶ ERROR
  │                                               │
  │                                        (response received)
  │                                               │
  │                                               ▼
  │                                         SPEAKING ──(barge-in)──▶ RECORDING
  │                                               │
  │                                        (done)  │
  └────────────────────────────────────────────────┘
  │
  ▼
RECONNECTING ──(Tailscale / WS down)──▶ IDLE (after reconnection)
```

### 4.3 Checkpoint Data Structure

```python
@dataclass
class Checkpoint:
    phase: str                        # Current phase
    last_transcript: str              # Last user speech text
    last_agent_response: str          # Last agent response
    last_agent_response_at: float     # Timestamp
    last_status_announced: str        # Last status spoken to user
    last_status_at: float             # When status was spoken
    agent_processing_started_at: float
    agent_processing_seconds: float
    pending_barge_in: bool
    error_count: int
    gateway_connected: bool           # True if WS is open
    last_gateway_disconnect_at: float # Timestamp of last disconnect
```

### 4.4 Status Announcement Schedule

The app checks its checkpoint every ~2 seconds during `AWAITING_REPLY`:

| Elapsed | TTS Announcement |
|---------|-----------------|
| < 3s | Silence (too fast to bother) |
| 3s | "One moment..." |
| 8s | "Still thinking..." |
| 20s | "This is taking longer than usual..." |
| 45s | "Let me try again." → abort + resend |

**New: Connectivity-specific announcements:**

| Event | TTS Announcement |
|-------|-----------------|
| Tailscale / WS disconnect | "Lost connection. Trying to reconnect..." |
| Reconnect successful | "Connection restored." |
| Pairing required (first run) | "I need to be paired with the cloud. Check your Gateway." |

### 4.5 Checkpoint Persistence

Write `data/checkpoint.json`:
- After each successful agent response
- Debounced to max once every 5s
- After a WS reconnect (reset `gateway_connected` + clear timers)
- On graceful shutdown

On restart with a non-IDLE checkpoint:
- Announce: "I'm back. I was in the middle of something."
- Resume listening (do NOT replay the message — avoid duplicate actions)

---

## 5. Gateway Configuration on the Cloud Server

### 5.1 Gateway is Remote

The Gateway runs on the **cloud server**, not on the Pi. You start it there:

```bash
# On the cloud server (your-gateway-hostname.ts.net)
openclaw gateway start

# Bind to the Tailscale interface for secure network access
# The Gateway should listen on the Tailscale IP
openclaw gateway status
```

### 5.2 Node Connection from the Pi

On the Pi, the node service connects to the same Gateway:

```bash
openclaw node run \
  --host "your-gateway-hostname.ts.net" \
  --port 443 \
  --tls \
  --display-name "minipupper-deepseek"
```

This registers the Pi as a **node** (capabilities: `system.run`, etc.). The
minipupper-app connects as a separate **operator** session — it speaks to the
same Gateway but with different scopes.

### 5.3 Network Verification

```bash
# On the Pi: verify Tailscale connectivity to the cloud server
ping -c 3 your-gateway-hostname.ts.net

# Test TLS WebSocket
curl -v telnet://your-gateway-hostname.ts.net:443

# Quick connectivity test
python3 -c "
import ssl, json
from websocket import create_connection
ws = create_connection(
    'wss://your-gateway-hostname.ts.net:443',
    ssl=ssl.create_default_context(),
    timeout=15
)
frame = json.loads(ws.recv())
print(f'Connected. Frame type: {frame.get(\"event\", \"unknown\")}')
ws.close()
"
```

### 5.4 Device Registration & Approval

The app's first connection will fail with `NOT_PAIRED`. Approve it on the
cloud server:

```bash
# On the cloud server: list pending pairing requests
openclaw nodes list --unapproved

# Approve the minipupper-app device
openclaw nodes pair approve --device-id "<device-fingerprint>"

# Optionally: auto-approve local tailnet connections
# (The app connects remotely, so manual approval is expected for first connection)
```

---

## 6. Implementation Plan

### 6.1 New File: `src/integration/openclaw_gateway.py`

Core Gateway WebSocket client with:
- `connect()` — TLS WS handshake with device identity, nonce signing, auth
- `_pair()` — first-run pairing flow
- `subscribe(session_key)` — subscribe to session events
- `send_transcript(text)` — send ASR text via `sessions.send`
- Incoming event handler — dispatches to TTS callback
- Checkpoint cache with periodic save and recovery
- Reconnect loop with exponential backoff
- Tailscale connectivity monitoring

```python
class OpenClawGatewayClient:
    """WebSocket client for the remote OpenClaw Gateway (Tailscale TLS)."""

    GATEWAY_URL = "wss://your-gateway-hostname.ts.net:443"

    def __init__(self, config):
        self.device_id = config["device_id"]
        self.device_key = self._load_key(config["key_path"])
        self.stored_token = config.get("token")
        self.on_response = None   # Callback: text → TTS
        self.on_status = None     # Callback: status text → TTS
        self.checkpoint = Checkpoint(...)
        self.ws = None
        self._loop_thread = None

    def _load_key(self, path): ...
    def _pair(self, nonce) -> str: ...
    async def connect(self):
        """Connect to remote Gateway over Tailscale TLS."""
        self.ws = create_connection(self.GATEWAY_URL, ssl=...)
        challenge = json.loads(await self.ws.recv())
        if self.stored_token:
            self._send_connect(challenge, self.stored_token)
        else:
            self.stored_token = self._pair(challenge["payload"]["nonce"])
            self._send_connect(challenge, self.stored_token)

    async def send_transcript(self, text: str) -> None:
        """Send ASR text to agent, setup wake for response."""
        self.checkpoint.phase = "SENDING_TO_AGENT"
        self.checkpoint.last_transcript = text
        self.checkpoint.agent_processing_started_at = time.time()
        await self.ws.send(json.dumps({
            "type": "req",
            "id": f"msg-{uuid4().hex[:8]}",
            "method": "sessions.send",
            "params": {"sessionKey": "main", "message": text},
        }))
        self._start_impatience_timer()

    async def _event_loop(self):
        """Process incoming frames."""
        async for frame_json in self.ws:
            frame = json.loads(frame_json)
            if frame["event"] == "session.message":
                msg = frame["payload"]["message"]
                if msg["role"] == "assistant":
                    self.checkpoint.last_agent_response = msg["content"]
                    self.checkpoint.last_agent_response_at = time.time()
                    self.checkpoint.phase = "SPEAKING"
                    if self.on_response:
                        self.on_response(msg["content"])
                elif msg.get("role") in ("tool", "system"):
                    if self.on_status:
                        self.on_status(msg["content"])
```

### 6.2 Modified: `minipupper_operator.py`

Add a mode switch in `config.yaml`:

```yaml
operator:
  mode: "openclaw"          # "openclaw" (remote Gateway over Tailscale)
                            # "local" (embedded Gemini — existing behavior)
```

When `mode: "openclaw"`:
- ASR output → `OpenClawGatewayClient.send_transcript()`
- Gateway response → TTS callback
- Checkpoint maintained internally
- Periodic status checks → status TTS announcements
- WS disconnect → enter RECONNECTING phase → speak "Lost connection"

### 6.3 New Config Sections

```yaml
# config/config.yaml — OpenClaw Gateway Integration

gateway:
  enabled: true
  url: "wss://your-gateway-hostname.ts.net:443"
  host: "your-gateway-hostname.ts.net"    # For TLS SNI
  # Device identity — auto-generated on first run unless overridden:
  device_id: ""
  device_key_path: "/home/ubuntu/.openclaw/minipupper-app-key.pem"
  device_token_path: "/home/ubuntu/.openclaw/minipupper-app-token.json"
  reconnect_interval_ms: 1000
  max_reconnect_interval_ms: 30000

checkpoint:
  enabled: true
  file: "data/checkpoint.json"
  status_announce_interval_sec: 5
  agent_impatience_sec:
    first_nudge: 3
    second_nudge: 8
    timeout: 45
```

### 6.4 New .env Variables

```env
# OpenClaw Gateway (Tailscale)
OPENCLAW_GATEWAY_URL=wss://your-gateway-hostname.ts.net:443
OPENCLAW_DEVICE_ID=
OPERATOR_MODE=openclaw       # "openclaw" or "local"
```

### 6.5 Node Boot Sequence

The Pi needs both services running. The boot order matters:

```
1. Tailscale connects (auto-started via systemd)
2. openclaw node run → connects Pi as node to cloud Gateway
3. minipupper-app starts → opens operator WS to same Gateway
4. Gateway sends session.message events → app speaks them
```

On startup, `minipupper_operator.py` should:
1. Test connectivity: `ping your-gateway-hostname.ts.net`
2. If unreachable → TTS: "I can't reach the cloud. Check your connection."
3. Try WS connect → if NOT_PAIRED → TTS: "I need to be paired first." (silent fallback)
4. Once connected → TTS: "Ready."

---

## 7. Files to Create / Modify

| File | Action | Purpose |
|------|--------|---------|
| `src/integration/__init__.py` | **Create** | Package init |
| `src/integration/openclaw_gateway.py` | **Create** | Gateway WS client with Tailscale TLS, pairing, checkpoint |
| `src/integration/device_identity.py` | **Create** | Key generation, signing, device ID management |
| `minipupper_operator.py` | **Modify** | Add `mode: "openclaw"` switch |
| `config/config.yaml` | **Modify** | Add `gateway` + `checkpoint` + `operator.mode` |
| `config/.env.sample` | **Modify** | Add `OPENCLAW_GATEWAY_*`, `OPERATOR_MODE` |
| `data/checkpoint.json` | **Create** (runtime) | Persisted state for crash recovery |

---

## 8. Edge Cases & Recovery

| Failure | Detection | Recovery |
|---------|-----------|----------|
| Tailscale not connected | `ping` fails or `tailscale status` shows offline | TTS: "Waiting for network..." → retry every 10s |
| Gateway not reachable | WS `connect()` timeout | TTS: "Can't reach the cloud." → retry backoff |
| First run / not paired | `NOT_PAIRED` error on connect | TTS: "Approval needed." → wait for pairing, then retry |
| Auth token stale | `AUTH_TOKEN_MISMATCH` | Re-run pairing flow, save new token |
| WS drops mid-conversation | `on_close` fires | Save checkpoint, TTS: "Lost connection." → reconnect + resend if incomplete |
| Agent > 45s | Checkpoint timer | Abort → TTS: "Let me try again" → resend transcript fresh |
| Empty ASR result | Empty string from Google Speech | Re-record silently (don't send empty) |
| Barge-in → empty follow-up | Short utterance | "I didn't catch that" → retry listening |
| TLS cert error (Tailscale) | SSL verify fail | Check Tailscale is up; `tailscale status` should show healthy |
| DNS resolution failure | Can't resolve hostname | TTS: "Can't find the cloud server" → check Tailscale connectivity |

---

## 9. Quick-Start Testing

### 9.1 Gateway Connectivity Test

```bash
# From the Pi — verify you can reach the Gateway over Tailscale TLS
python3 -c "
import ssl, json
from websocket import create_connection

url = 'wss://your-gateway-hostname.ts.net:443'
ctx = ssl.create_default_context()
ctx.check_hostname = True

ws = create_connection(url, ssl=ctx, timeout=15)
frame = json.loads(ws.recv())
print(f'Challenge received: {frame[\"event\"]}')
ws.close()
print('TLS WebSocket OK — Gateway is reachable')
"
```

### 9.2 Full Pipeline Test

```bash
OPERATOR_MODE=openclaw python scripts/test_pipeline.py --continuous
```

This should:
1. Record from mic
2. ASR → transcript
3. Send to remote Gateway via Tailscale TLS
4. Wait for response (possibly delayed by Tailscale RTT)
5. Speak response through TTS
6. Support barge-in during speaking

### 9.3 Pairing Walkthrough

First run will fail with `NOT_PAIRED`. Approve on the cloud server:

```bash
# On cloud server:
openclaw nodes list --unapproved
openclaw nodes pair approve --device-id "<printed by the app>"
```

Then restart the app — it will find the stored token and connect successfully.

---

## 10. Security Notes

- **All Gateway traffic is over Tailscale** — encrypted end-to-end via WireGuard
  + TLS. No traffic leaves the tailnet.
- **Device identity** — the app signs each connect challenge with its private
  key. The Gateway verifies the public key fingerprint.
- **Tokens are stored on disk** — `~/minipupper-app/config/.env` and
  `~/.openclaw/*.json`. Keep permissions `0600`.
- **No internet exposure** — the Gateway only listens on the Tailscale IP
  (private tailnet address). Only machine on the tailnet can connect.
- **First-connection pairing** ensures that only authorised devices can
  connect as operators to the Gateway.
