# Minipupper Operator - Architecture & Design

**Last Updated:** 2026-05-09  
**Status:** Early Design  
**Revision:** 0.1

---

## 1. System Overview

The Minipupper Operator is a **standalone, voice-first conversational agent** running on Minipupper (Debian-based Raspberry Pi). It provides robust autonomous capabilities without depending on OpenClaw for core operation.

### Key Principles
- **Operator-First:** Direct, autonomous robot control
- **Barge-in Ready:** User can interrupt TTS at any time
- **Low Latency:** Speech-to-response < 1 second goal
- **Queue-Based:** Decoupled components via thread-safe queues
- **Tailscale Connected:** Cloud-gateway via secure mesh network

---

## 2. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                     MINIPUPPER ROBOT                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │         AUDIO I/O LAYER (src/audio/)                     │  │
│  │                                                           │  │
│  │  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐   │  │
│  │  │ Barge-in    │  │ Audio Manager│  │ ASR (Whisper)│   │  │
│  │  │ Detector    │  │ (TTS/ASR)    │  │ (faster-wh)  │   │  │
│  │  └─────────────┘  └──────────────┘  └──────────────┘   │  │
│  │       │                    │                   │         │  │
│  │       └────────────────────┴───────────────────┘         │  │
│  │                       │                                  │  │
│  └───────────────────────┼──────────────────────────────────┘  │
│                          │                                     │
│  ┌───────────────────────▼──────────────────────────────────┐  │
│  │       CORE LOGIC LAYER (src/core/)                      │  │
│  │                                                           │  │
│  │  ┌────────────────────────────────────────────────────┐ │  │
│  │  │     MinipupperOperator (Main Application)          │ │  │
│  │  │                                                     │ │  │
│  │  │  • ASR Worker (speech → text)                      │ │  │
│  │  │  • Operator Worker (text → response, LLM)          │ │  │
│  │  │  • Movement Worker (execute commands)              │ │  │
│  │  │  • Control Worker (system commands)                │ │  │
│  │  │                                                     │ │  │
│  │  └────────────────────────────────────────────────────┘ │  │
│  │                                                           │  │
│  │  ┌──────────────────────────────────────────────────┐   │  │
│  │  │  Task Queue System (Inter-Process Communication) │   │  │
│  │  │  • input_text_queue (ASR → Operator)             │   │  │
│  │  │  • output_text_queue (Operator → TTS)            │   │  │
│  │  │  • barge_in_detected (Audio → Audio Manager)     │   │  │
│  │  │  • movement_queue (Operator → Movement)          │   │  │
│  │  │  • status_queue (All → Status broadcast)         │   │  │
│  │  └──────────────────────────────────────────────────┘   │  │
│  │                                                           │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │      ROBOT CONTROL LAYER (src/robot/)                   │  │
│  │                                                           │  │
│  │  ┌──────────────┐  ┌───────────┐  ┌─────────────────┐   │  │
│  │  │ Movement API │  │  Sensors  │  │  Vision Module  │   │  │
│  │  │ (Motor Ctrl) │  │ (IMU, etc)│  │  (Camera, pose) │   │  │
│  │  └──────────────┘  └───────────┘  └─────────────────┘   │  │
│  │                                                           │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                            │
                    ┌───────▼────────┐
                    │   Tailscale    │ (Secure mesh network)
                    └────────────────┘
                            │
                    ┌───────▼────────┐
                    │ Cloud Gateway  │ (Optional services)
                    └────────────────┘
```

---

## 3. Component Details

### 3.1 Audio I/O Layer

#### Barge-in Detector (`src/audio/barge_in_detector.py`)
- **Purpose:** Detect user speech during robot speech
- **Mechanism:** Energy-based detection + optional VAD
- **Latency:** ~500ms detection window
- **Output:** Interrupt signal to Audio Manager
- **Config:** `config.yaml` → `barge_in.*`

#### Audio Manager (`src/audio/audio_manager.py`)
- **Input:** User speech (microphone) → ASR
- **Processing:** Whisper/faster-whisper (local GPU/CPU)
- **Output:** Text to Operator; Audio from TTS
- **Features:**
  - Streaming ASR for low latency
  - Google Cloud TTS with multiple voices
  - Interruptible playback (barge-in support)
- **Config:** `config.yaml` → `audio.*`

### 3.2 Core Logic Layer

#### Task Queue System (`src/core/task_queue.py`)
- **Architecture:** Thread-safe Python queues
- **Decoupling:** Loose coupling between components
- **Benefits:**
  - Each worker can scale independently
  - Easy to add new workers
  - No circular dependencies

**Queue Map:**
| Queue | Producer | Consumer | Purpose |
|-------|----------|----------|---------|
| `input_text_queue` | ASR Worker | Operator Worker | Transcribed user speech |
| `output_text_queue` | Operator Worker | TTS/Display | Response text to speak |
| `barge_in_detected` | Barge-in Detector | Audio Manager | Interrupt signal |
| `speech_active` | Audio Manager | ASR Worker | Mute during robot speech |
| `movement_queue` | Operator Worker | Movement Worker | Robot movement commands |
| `status_queue` | All Workers | UI/Logger | Status updates & telemetry |
| `control_queue` | External | Control Worker | System commands (shutdown, restart) |

#### MinipupperOperator (`minipupper_operator.py`)
- **Main Application Class:** Central coordinator
- **Responsibilities:**
  - Initialize all subsystems
  - Start/stop worker threads
  - Load configuration
  - Manage application lifecycle
  
- **Workers:**
  1. **ASR Worker** - Listens for user speech, transcribes
  2. **Operator Worker** - Processes input, generates responses (LLM-based)
  3. **Movement Worker** - Executes movement/action commands
  4. **Control Worker** - Handles system control (shutdown, restart)

### 3.3 Robot Control Layer

#### Movement API (`src/robot/movement_api.py`) - *To be implemented*
- Wrapper around Minipupper motor control
- Commands: sit, stand, move_forward, move_backward, turn, etc.
- Safety checks: collision detection, speed limits
- Status feedback: current pose, battery level

#### Sensor Integration (*To be implemented*)
- IMU for pose estimation
- Distance sensors for obstacle avoidance
- Camera for vision-based tasks

---

## 4. Data Flow - Conversation Example

```
User:   "Stand up and look around"
         │
         ▼
[Audio captured by microphone]
         │
         ▼
┌─────────────────────────────────┐
│ Barge-in Detector (monitoring)  │
└──────────────┬──────────────────┘
         │
         ▼
[ASR: Whisper (faster-whisper)]
Transcribed: "Stand up and look around"
         │
         ▼
┌───────────────────────────────────┐
│ input_text_queue                  │
└──────────┬────────────────────────┘
         │
         ▼
┌────────────────────────────────────┐
│ Operator Worker                    │
│ Process: "Stand up and look around"│
│ LLM Response: "I'll stand and      │
│ look around now"                   │
│ Move Commands: [stand, look_around]│
└─────────┬──────────────────────────┘
         │
         ├──────────────────┬──────────────────┐
         │                  │                  │
         ▼                  ▼                  ▼
  output_text_queue  movement_queue    status_queue
         │                  │                  │
         ▼                  ▼                  ▼
  Audio Manager      Movement Worker    Logger/UI
  (speak response)   (execute movement) (status updates)
         │                  │
         ▼                  ▼
[Robot speaks while standing and looking around]
```

**Barge-in During Speech:**
```
Robot speaking: "I'll stand and look around now"
         │
         ▼
User interrupts: [speaks over robot]
         │
         ▼
[Barge-in Detector detects speech energy above threshold]
         │
         ▼
[Sends interrupt signal to Audio Manager]
         │
         ▼
[TTS playback stops immediately]
         │
         ▼
[Operator processes new user input, if any]
```

---

## 5. Configuration Management

### Configuration Hierarchy (lowest to highest priority)
1. **Defaults** (hardcoded in Python)
2. **YAML File** (`config/config.yaml`)
3. **Environment Variables** (`.env` file)
4. **Runtime API** (if supported)

### Key Configuration Sections

**Audio Settings** (`config.yaml` → `audio`)
```yaml
audio:
  asr:
    engine: "faster_whisper"  # ASR engine choice
    model: "base"  # Model size
    device: "cuda"  # Accelerator
    streaming: true  # Streaming ASR
  tts:
    engine: "google"  # TTS provider
    voice: "en-US-Neural2-A"  # Voice selection
    speed: 1.0  # Speech speed multiplier
```

**Barge-in Settings** (`config.yaml` → `barge_in`)
```yaml
barge_in:
  enabled: true
  min_energy_threshold: 500  # Tune based on ambient noise
  detection_timeout_ms: 500  # How fast to respond
  silence_duration_ms: 300  # Debounce
  voice_activity_threshold: 0.5  # VAD confidence (0-1)
```

**Operator Settings** (`config.yaml` → `operator`)
```yaml
operator:
  role: "minipupper_autonomous"  # Role identifier
  max_context_length: 8192  # LLM context window
  response_timeout_seconds: 30  # Max wait for response
  enable_tool_execution: true  # Allow robot commands
```

---

## 6. Thread Safety & Concurrency

### Queue-Based Synchronization
- All queues are thread-safe Python `queue.Queue`
- Workers communicate only via queues (no shared memory)
- Non-blocking `get_nowait()` with timeout handling

### Worker Lifecycle
```
Application Start
    │
    ├─► ASR Worker (thread)
    ├─► Operator Worker (thread)
    ├─► Movement Worker (thread)
    └─► Control Worker (thread)
    
Application Stop (graceful shutdown)
    │
    ├─► Set _stop_event flag
    │
    ├─► Workers check is_running/stop_event
    │
    └─► Threads join with timeout
```

### Avoiding Deadlocks
- No circular queue dependencies
- All `get()` calls use timeout
- Proper exception handling in workers
- Clean shutdown sequence

---

## 7. Expansion Points

### How to Add New Capabilities

**1. Add a New Movement Command**
```
In movement_api.py:
  └─ def new_movement(): ...
  
In minipupper_operator.py:
  └─ movements dict: {"new_cmd": new_movement}
```

**2. Add a New Sensor**
```
In src/robot/sensors.py (new file):
  └─ Sensor class with read() method
  
In minipupper_operator.py:
  └─ sensor_worker() thread
  └─ Put data into a sensor_queue
```

**3. Add a New LLM Provider**
```
In operator_worker():
  └─ Switch on config['operator']['llm_provider']
  └─ Call appropriate API/model
```

**4. Add a New Audio Engine**
```
In audio_manager.py:
  └─ Support multiple TTS/ASR engines
  └─ Switch via config
```

---

## 8. Performance Considerations

### Latency Targets
- **Speech→Text (ASR):** < 2 seconds (streaming)
- **Text→Response (LLM):** < 1 second (small model) to 5 seconds (large)
- **Response→Audio (TTS):** < 1 second
- **Total Conversation Latency:** < 5 seconds goal

### Resource Constraints (Raspberry Pi 4 / 8GB)
- **CPU:** 4 cores @ 1.8 GHz
- **Memory:** 8 GB RAM
- **Storage:** SDCard (typical 64-128 GB)
- **Compute:** Optional USB TPU/GPU

### Optimization Strategies
1. **Model Quantization** - Use 4-bit/8-bit quantized LLMs
2. **Streaming ASR** - Don't wait for full audio
3. **Local Models** - Avoid cloud API latency
4. **Thread Pooling** - Reuse threads (Python threading)
5. **Queue Monitoring** - Drop old items if processing slow

---

## 9. Failure Modes & Recovery

| Failure | Detection | Recovery |
|---------|-----------|----------|
| ASR Timeout | No speech for N seconds | Reset microphone stream |
| LLM Timeout | Response not generated in time | Return fallback response |
| TTS Failure | Audio synthesis error | Log error, continue |
| Barge-in False Positive | Repeated interrupts | Increase threshold |
| Network Down | Can't reach cloud | Use local-only mode |
| Memory Leak | Memory growing | Restart worker threads |

---

## 10. Testing Strategy

### Unit Tests
- Barge-in detector (speech detection accuracy)
- Audio manager (ASR/TTS integration)
- Queue operations (thread safety)
- Configuration loading

### Integration Tests
- Full conversation flow (speech → response → speech)
- Barge-in during TTS (interrupt handling)
- Movement command execution
- Queue overflow handling

### System Tests
- Long-running stability (24+ hours)
- Network failure scenarios (Tailscale down)
- High-load concurrency
- Memory profiling

---

**Revision History:**
- **v0.1** (2026-05-09) - Initial architecture, early design

**Next Review:** 2026-05-15
