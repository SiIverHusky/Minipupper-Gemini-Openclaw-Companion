## Script Invocation Capability

### Overview
The Mini Pupper Operator (Phase 3) supports multiple script invocation paths for executing actions on the robot. Both the Operator itself and the OpenClaw agent can invoke scripts.

### Invocation Methods

#### 1. OpenClaw Task Queue (`tasks.json`)
- **File:** `~/.openclaw/workspace/minipupper/tasks.json` (old) or `~/minipupper-app/tasks.json` (new)
- **Flow:** Operator writes `{"tasks": {"task-id": {"action": "...", "params": {...}}}}` → Agent reads, processes, writes result
- **Actions supported:** `explore`, `web_search`, `web_fetch`, `query`, `implement`, `robot.*` (move, activate, set_mode, take_photo, etc.)
- **Protocol:** `protocol.py` defines structured JSON messages (`TaskMessage`, `StatusMessage`, `ResultMessage`)

#### 2. Robot Control Script (`minipupper_control.py`)
- **Path:** `~/minipupper_control.py`
- **Usage:** `python3 ~/minipupper_control.py {subcommand} {duration}`
- **Subcommands:** activate, deactivate, trot, walk, stop, forward, backward, left, right, turn, dance, reset, raise_body, lower_body, rest
- **Mechanism:** Sends UDP joystick messages (msgpack) to port 8830, 127.0.0.1

#### 3. Utility Scripts (`~/minipupper-app/scripts/`)
| Script | Purpose |
|--------|---------|
| `capture_and_show.py` | Capture photo from MIPI camera + display on ST7789 LCD |
| `calibrate_aec.py` | Calibrate Acoustic Echo Cancellation |
| `manage_archives.py` | Manage audio/capture archives |
| `send_wake.py` | Send wake signal |
| `test_bargein.py` | Test barge-in detection |
| `test_pipeline.py` | Test audio pipeline |
| `start_with_aec.sh` | Start with AEC enabled |

#### 4. Custom Modules (`~/minipupper-app/custom/`)
- **Already deployed:** `camera_person_follow/main.py` (HOG people detector + robot follower)
- **Deployed standalone:** `camera_person_follower.py` (MOG2 background subtraction variant)

#### 5. Operator Internal Script Invocation
- `minipupper_operator.py` uses thread-safe queues: `movement_queue`, `control_queue`, `openclaw_queue`, `status_queue`
- Movement is parsed from Gemini NL output and dispatched to `_execute_movement()`
- Complex tasks (web, exploration) are offloaded to OpenClaw agent via tasks.json

### Available Hardware
- **CPU:** Raspberry Pi (ARM64)
- **Camera:** MIPI CSI at /dev/video0, 640x480 via OpenCV 4.10
- **Libraries:** OpenCV, NumPy, PIL, SciPy, scikit-learn (no PyTorch or TensorFlow)
- **Display:** ST7789 LCD 320x240 (via `MangDang.mini_pupper.display`)
- **Robotics:** ESP32Interface for IMU, power, servo control; UDP joystick on port 8830
- **Audio:** ALSA devices for mic/speaker, Google Cloud Speech STT/TTS, barge-in support

### Creating New Scripts
1. Add invocation-capable scripts to `~/minipupper-app/custom/{topic}/main.py`
2. Add supporting scripts to `~/minipupper-app/scripts/`
3. For OpenClaw tasks: agent handles execute actions with `host="node"`, `node="minipupper-deepseek"`
4. Robot control: Use `minipupper_control.py` or direct UDP Publisher to port 8830

### Task Flow (Operator → Agent)
1. Operator LLM (Gemini) decides to offload → writes task to tasks.json
2. Agent (this session) picks up task during heartbeat/cron → processes → writes result
3. Operator TaskWatcher polls tasks.json → passes result to LLM → announces via TTS
