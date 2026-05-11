# Minipupper Operator — Setup Guide

A voice-controlled AI assistant for your Mini Pupper robot. Speak commands, and
the robot responds — answering questions, moving around, taking photos, and more.

> **How it works:** The robot runs two services that connect to an OpenClaw
> Gateway server in the cloud. A voice app on the Pi transcribes your speech,
> processes it through Gemini, and offloads complex tasks to the Gateway
> where an agent processes them (web searches, robot movement, camera, etc.).

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Prerequisites](#prerequisites)
3. [Setup: Gateway Server](#setup-gateway-server)
4. [Setup: Mini Pupper (Pi)](#setup-mini-pupper-pi)
5. [Running Everything](#running-everything)
6. [Hardware Support](#hardware-support)
7. [Common Issues](#common-issues)
8. [Monitoring](#monitoring)

---

## Architecture Overview

```
┌──────────────────────────────────┐      ┌──────────────────────────────┐
│   Mini Pupper (Raspberry Pi)    │      │     OpenClaw Gateway (Cloud)  │
│                                  │      │                              │
│  ┌──────────────────────────┐   │      │  ┌────────────────────────┐  │
│  │  openclaw node run       │──┼──────┼──│  Node connection        │  │
│  │  (node-host service)     │   │ Tail │  │  (exec on Pi, file     │  │
│  └──────────────────────────┘   │ scale │  │   access, system.run)  │  │
│                                  │  TLS  │  └────────────────────────┘  │
│  ┌──────────────────────────┐   │       │                              │
│  │  minipupper_operator.py  │──┼──────┼──│  ┌────────────────────────┐  │
│  │  (voice app)             │   │       │  │  Operator WebSocket     │  │
│  │                          │   │       │  │  (cron.run via RPC,     │  │
│  │  • Google Cloud STT/TTS  │   │       │  │   session subscription)│  │
│  │  • Gemini 2.5 Flash LLM  │   │       │  └────────────────────────┘  │
│  │  • File-based protocol   │   │       │                              │
│  │  • Camera + LCD display  │   │       │  ┌────────────────────────┐  │
│  └──────────────────────────┘   │       │  │  Cron job (disabled)   │  │
│                                  │       │  │  Runs on-demand via   │  │
│  Shared file:                    │       │  │  cron.run RPC          │  │
│  ~/minipupper-app/tasks.json ────┼───────┼──│  Processes tasks in    │  │
│                                  │       │  │  isolated session      │  │
│  (app writes pending tasks,      │       │  └────────────────────────┘  │
│   Gateway cron reads & writes    │       │                              │
│   results back)                  │       └──────────────────────────────┘
└──────────────────────────────────┘
```

### Two Connections, One Purpose

The Pi establishes **two independent connections** to the Gateway, and **both
are required** for full functionality:

| Connection | Role | What it provides |
|------------|------|-----------------|
| `openclaw node run` | **Node** | `exec` access to the Pi (read/write files, run commands). Used by the cron to process tasks. |
| `minipupper_operator.py` | **Operator** | WebSocket for `cron.run` RPC calls, session subscription. Used by the app to trigger task processing. |

> **Piggybacking on the node:** The app doesn't have its own `exec` access
> to the Pi. Instead, it writes tasks to a shared file (`tasks.json`). The
> Gateway cron reads this file via the **node connection**, processes the task
> using `exec` on the Pi, and writes back the result. The app detects the
> completed task and announces it. The node connection is the workhorse — the
> app itself just handles voice I/O and Gemini.

### Task Flow

```
User speaks → Google STT → Gemini LLM
  ├── Simple conversation? → Answer directly (no TASK)
  └── Complex task? → Outputs [TASK] marker
       │
       ▼
App writes to ~/minipupper-app/tasks.json  (status: pending)
App sends cron.run via WebSocket
       │
       ▼
Gateway cron fires (isolated session, ~8-12s cold start)
  ├── Reads tasks.json via node exec
  ├── Processes: web_search / robot.* / robot.take_photo_and_show / etc.
  └── Writes result back (status: completed)
       │
       ▼
App's TaskWatcher detects completion (polls every 2s)
  ├── Feeds result into Gemini for natural TTS
  └── Speaks: "I checked — it's 28°C in Hong Kong!"
```

### Why No Periodic Polling?

The cron job is **disabled by default**. It only runs when the app explicitly
calls `cron.run` via the Gateway WebSocket RPC. This means:
- **Zero wasted resources** between tasks
- **Zero LLM cold starts** when idle
- Each task pays only its own ~8-12s cold start cost

---

## Prerequisites

### Hardware
- Mini Pupper v2 (Raspberry Pi CM4 / Pi 4)
- Microphone + speaker connected (USB audio or I2S)
- (Optional) MIPI camera module + ST7789 SPI LCD display
- Power supply for the robot

### Software
- **Pi:** Ubuntu 22.04 / Debian 11, Python 3.10+, Tailscale
- **Cloud server:** OpenClaw Gateway (this repository's environment)
- **Accounts:** Google Cloud (STT/TTS/Vertex AI), Tailscale

### Google Cloud API Access
Three Google Cloud APIs are needed:
1. **Speech-to-Text** — transcribes your speech
2. **Text-to-Speech** — speaks responses
3. **Vertex AI (Gemini 2.5 Flash)** — language understanding

Create a service account and download the JSON key. Enable all three APIs in
your Google Cloud project.

---

## Setup: Gateway Server

The Gateway server should already be running. Verify:

```bash
# Check Gateway status
openclaw status

# Verify the cron job exists (should be disabled)
openclaw cron list --include-disabled
# Expected: minipupper-task-runner (id: 5f1ccf26-...)
```

> The cron job is intentionally **disabled**. It is triggered on-demand
> by the app. Do not enable it for periodic polling.

---

## Setup: Mini Pupper (Pi)

### 1. Install OpenClaw on the Pi

```bash
curl -fsSL https://openclaw.ai/install.sh | sh
```

This creates the device identity at `~/.openclaw/identity/device.json`.

### 2. Set up Tailscale

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

### 3. Set up the Operator App

```bash
cd ~
git clone https://github.com/mangdangroboticsclub/minipupper-app.git
cd minipupper-app
python3.10 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp config/.env.sample config/.env
```

Edit `config/.env` and fill in:
```bash
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
GOOGLE_CLOUD_PROJECT_ID=your-project-id
OPENCLAW_GATEWAY_URL=wss://instance-xxxxx.tailXXXXX.ts.net:443/ws
```

Edit `config/config.yaml` and verify the `network` section:
```yaml
network:
  tailscale_enabled: true
  gateway_url: ${OPENCLAW_GATEWAY_URL}
  session_target: agent:main:dashboard:<dashboard-session-key>
  cron_job_id: <cron-job-id>
```

### 4. Start the Node Connection

The node provides `exec` access to the Pi — the Gateway cron needs this to
read/write files and run commands. Without the node, **nothing works**.

```bash
# In one terminal
openclaw node run --host "instance-xxxxx.tailXXXXX.ts.net" --port 443 --tls
```

The Gateway will show a pending pairing request. Approve it:

```bash
# On the Gateway server
openclaw devices list                # Find the request ID
openclaw devices approve <request-id>
```

> **First-time pairing:** Node connects → Gateway sees new device → pending
> approval → you approve → node reconnects → connected.

### 5. Start the Operator App

```bash
cd ~/minipupper-app
source venv/bin/activate
python minipupper_operator.py
```

Expected startup output:
```
✓ Google Cloud Speech-to-Text initialized
✓ Google Cloud TTS initialized
✓ Gemini Vertex AI ready (model: gemini-2.5-flash)
✓ Minipupper Operator running. Listening for speech...
Connected to Gateway (device: ec03b99a...)
```

### 6. (Optional) Auto-start with systemd

**Node service:**
```bash
sudo tee /etc/systemd/system/openclaw-node.service << 'SERVICEEOF'
[Unit]
Description=OpenClaw Node Host - minipupper-deepseek
After=network-online.target tailscaled.service
Wants=network-online.target tailscaled.service

[Service]
Type=simple
User=ubuntu
ExecStartPre=/usr/bin/sleep 3
ExecStart=/home/ubuntu/.npm-global/bin/openclaw node run \
  --host "instance-xxxxx.tailXXXXX.ts.net" --port 443 --tls
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SERVICEEOF

sudo systemctl enable --now openclaw-node
```

---

## Running Everything

The minimum setup requires **two running processes** on the Pi:

```bash
# Terminal 1: Node connection (provides exec access)
openclaw node run --host "..." --port 443 --tls

# Terminal 2: Operator app (voice + task offloading)
cd ~/minipupper-app && source venv/bin/activate && python minipupper_operator.py
```

Once both are connected:

1. **Speak into the microphone** — the app transcribes and processes through Gemini
2. **Gemini decides** — simple chitchat is handled directly, complex tasks get
   `[TASK]` markers
3. **File is written** — the app creates a pending task in `tasks.json`
4. **Cron fires** — the app calls `cron.run` via WebSocket
5. **Task processes** — the cron reads the file via node exec, does the work,
   writes the result
6. **Voice response** — the app detects the completed task and speaks the answer

### Example Commands

| You say | What happens |
|---------|-------------|
| "What's the weather in Hong Kong?" | Gemini → web_search → result spoken |
| "Take a step to the right" | Gemini → robot movement via UDP joystick |
| "Look left, right, up, down" | Gemini → 4 sequential [TASK] markers → compound execution |
| "Take a picture and show it on screen" | Gemini → camera capture → displays on ST7789 LCD |
| "How are you doing?" | Gemini answers directly (no TASK needed) |

---

## Hardware Support

### Camera + Display (Optional)

If your Mini Pupper has the MIPI camera module and ST7789 LCD display:

| Component | Interface | Library |
|-----------|-----------|---------|
| Camera | `/dev/video0` | OpenCV (`cv2.VideoCapture(0)`) |
| Display | SPI (ST7789, 320x240) | `MangDang.mini_pupper.display.Display` |

Script: `~/minipupper-app/scripts/capture_and_show.py`

```bash
# Capture + show on screen
python ~/minipupper-app/scripts/capture_and_show.py

# Capture + show + save to file
python ~/minipupper-app/scripts/capture_and_show.py --save /tmp/photo.jpg

# Show an existing image
python ~/minipupper-app/scripts/capture_and_show.py --display-only /tmp/photo.jpg
```

### Robot Movement (UDP Joystick)

The robot controller receives UDP messages on port 8830. The web controller
(`web-controller` on port 8080) provides a web UI. Movement commands are
triggered by the Gateway cron via exec scripts on the Pi.

---

## Common Issues

### 1. "Device metadata change pending approval" (Node re-pair)

**Symptom:** After a Pi reboot, `openclaw node run` fails with:
```
device metadata change pending approval (requestId: ...)
```

**Cause:** The Pi's device identity file persists across reboots, but other
metadata (hostname, Tailscale IP, kernel version) changes. The Gateway flags
this as a metadata change requiring re-approval.

**Fix:**
```bash
# On the Gateway server
openclaw devices list                # Note the request ID
openclaw devices approve <request-id>
```

This only happens once per reboot. After approval, subsequent reconnections
succeed without re-approval.

**Prevention:** Set up `openclaw-node.service` systemd unit for auto-reconnect.

### 2. "Scope upgrade pending approval" (cron.run fails)

**Symptom:** The app writes a task, logs "Triggered cron 5f1ccf26...", but the
cron never fires. The task sits in `tasks.json` as `pending` forever.

**Cause:** The app's Gateway WebSocket needs `operator.admin` scope to call
`cron.run`. If paired with only `operator.read,operator.write`, the RPC is
silently rejected.

**Verify:**
```bash
openclaw devices list | grep "<app-device-id>"
# Scopes should include: operator.admin
```

**Fix:**
1. Add `operator.admin` to `SCOPES` in `src/openclaw/client.py`:
   ```python
   SCOPES = ['operator.admin', 'operator.read', 'operator.write']
   ```
2. Restart the app → it requests the new scope → pending upgrade appears
3. Approve:
   ```bash
   openclaw devices approve <request-id>
   ```

### 3. "Gateway response: Okay, it was skipped" (Noise loop)

**Symptom:** The app logs "Gateway response: ..." every 3-5 seconds. Messages
say "Skipped!" or "Everything is okay!" even when idle.

**Cause:** Legacy code path summarized cron session events through Gemini.
Already fixed — the app now filters out cron session messages and silently
drops non-protocol messages.

### 4. App writes task but nothing processes it

**Symptom:** Task sits in `tasks.json` as `pending` forever.

**Checklist:**
1. Is the **node connection** active? (`openclaw nodes status`)
2. Does the app device have **`operator.admin` scope**? (See #2)
3. Is the **cron job** present and disabled? (`openclaw cron list --include-disabled`)
4. Did the **app restart** after config changes?

### 5. "Everything is all clear!" (Harmless snapshot)

A single "Gateway response" at startup or every 30s is normal — it's the
Gateway's periodic session snapshot. Only `minipupper-v1` protocol messages
trigger announcements; everything else is silently dropped.

---

## Monitoring

### On the Pi

```bash
cat ~/minipupper-app/tasks.json              # Current task state
tail -f ~/minipupper-app/logs/minipupper_operator.log  # App logs
python ~/minipupper-app/scripts/manage_archives.py stats  # Archive stats
```

### On the Gateway

```bash
openclaw cron list --include-disabled           # Cron job status
openclaw cron runs --id 5f1ccf26-...            # Run history
openclaw nodes status                           # Node connection
openclaw devices list                           # All paired devices
openclaw logs --follow --json | grep -i minipupper  # Live logs
```

### Manual Task Signaling

```bash
# Trigger cron immediately (from Gateway server)
openclaw gateway call cron.run --params '{"id":"5f1ccf26-..."}'

# Send wake signal (from Pi, standalone)
python ~/minipupper-app/scripts/send_wake.py
```

---

## File Reference

### Pi (`~/minipupper-app/`)

| File | Purpose |
|------|---------|
| `minipupper_operator.py` | Main app entry point |
| `config/config.yaml` | App configuration |
| `config/system_prompt_phase2.txt` | Gemini prompt with TASK offloading |
| `src/core/task_watcher.py` | Polls tasks.json, announces via TTS |
| `src/core/task_archiver.py` | Archives completed tasks by date |
| `src/core/llm_engine.py` | LLM provider abstraction |
| `src/audio/audio_manager.py` | Google Cloud STT + TTS with barge-in |
| `src/openclaw/client.py` | Gateway WebSocket client |
| `scripts/capture_and_show.py` | Camera capture + LCD display |
| `scripts/send_wake.py` | Standalone cron trigger |
| `scripts/manage_archives.py` | Archive management CLI |
| `tasks.json` | Shared task file (live state) |
| `tasks_archive/` | Archived task history |

### Gateway (`~/.openclaw/workspace/`)

| File | Purpose |
|------|---------|
| `HEARTBEAT.md` | Heartbeat task instructions |
| `minipupper/task_handler.py` | Action router |
| `minipupper/protocol.py` | Protocol message types |

---

## Architecture Notes

### Why the Node + Operator Split?

The Gateway distinguishes between two device roles:

- **Node:** A device that allows `exec` commands — the workhorse. The Gateway
  runs shell commands on the Pi through this connection.
- **Operator:** A device with WebSocket access — the coordinator. It calls
  `cron.run` and subscribes to session messages.

The app needs **both**:
- The **operator** connection sends `cron.run` to trigger processing
- The **node** connection executes the actual work (reading files, running
  camera scripts, sending UDP joystick commands)

They piggyback on the **same device identity**
(`~/.openclaw/identity/device.json`) but negotiate different roles.

### Why File-Based Protocol?

Earlier versions used session-based messaging (WebSocket messages for task
data). Problems encountered:

- **Message pollution:** Stale messages from old sessions replayed
- **"Skipped" spam:** Non-priority messages looped endlessly
- **Session mismatch:** App subscribed to one session, replies went elsewhere

The file-based approach is simpler:
1. App writes to a file on the Pi's filesystem
2. Gateway reads/writes the same file via the node connection
3. No message routing, no session management — just a shared JSON file
