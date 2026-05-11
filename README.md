# Gemini-Openclaw: Voice-First AI Companion for Minipupper

A **voice-first conversational AI assistant** for Minipupper robots that leverages Google Gemini and delegates complex tasks to OpenClaw. This project provides autonomous capabilities with **barge-in support** (users can interrupt the robot's speech at any time) and real-time voice interaction.

## 🎯 Project Goals

- **Voice-First Interaction** — Natural speech-in, speech-out conversation with the Minipupper robot
- **Task Delegation** — Delegate complex operations (web search, robot control, tool orchestration) to OpenClaw while keeping voice lightweight and responsive
- **Barge-In Ready** — User can interrupt robot speech for stopping output
- **Production Ready** — Hardened for 24/7+ operation with reliability and recovery mechanisms

## 📁 Project Structure

```
.
├── minipupper-app/           # Main voice assistant application
│   ├── src/
│   │   ├── audio/            # Audio pipeline (ASR, TTS, barge-in detection)
│   │   ├── core/             # Core logic (LLM, task queue, task watcher, protocol handler)
│   │   ├── openclaw/         # OpenClaw client and integration
│   │   └── robot/            # Robot movement APIs
│   ├── config/               # Configuration files (YAML, environment samples)
│   ├── scripts/              # Utility scripts (testing, calibration, archiving)
│   ├── docs/                 # Comprehensive documentation (setup, architecture, deployment)
│   ├── minipupper_operator.py # Main application entry point
│   ├── protocol.py           # File-based task protocol handler
│   └── requirements.txt      # Python dependencies
│
├── reference/                # Reference implementations
│   ├── ai-app/              # Original queue-based AI app architecture
│   ├── api/                 # Google API integrations
│   ├── facial-expression-app/ # Facial expression detection
│   └── gesture-detection-app/ # Hand gesture detection
│
├── docs/                     # Root-level documentation
│   ├── Design.md            # System architecture and design decisions
│   └── Pairing.md           # OpenClaw integration protocol guide
│
└── README.md                # This file
```

## 🚀 Quick Start

### Prerequisites

- **Minipupper Robot** with Raspberry Pi 4 (4GB+ RAM)
- **Python 3.9+** installed
- **Microphone + speakers** connected to the robot
- **Google Cloud Account** with credentials for STT, TTS, and Vertex AI (Gemini)
- **Optional:** OpenClaw server for task delegation (can run without it initially)

### Installation (5 minutes)

```bash
# 1. Clone the repository
cd /path/to/your/workspace
git clone <repo-url>
cd Gemini-Openclaw

# 2. Navigate to the app
cd minipupper-app

# 3. Create Python environment
python3.10 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Set up credentials
cp config/.env.sample config/.env
# Edit config/.env with your Google Cloud credentials

# 6. Run the application
python minipupper_operator.py
```

For detailed setup instructions, see [minipupper-app/QUICKSTART.md](minipupper-app/QUICKSTART.md).

## 📚 Documentation Overview

### For Getting Started
- **[minipupper-app/QUICKSTART.md](minipupper-app/QUICKSTART.md)** — 5-minute setup guide
- **[minipupper-app/docs/SETUP_GUIDE.md](minipupper-app/docs/SETUP_GUIDE.md)** — Comprehensive installation with Google Cloud setup

### For Understanding the System
- **[minipupper-app/docs/ARCHITECTURE.md](minipupper-app/docs/ARCHITECTURE.md)** — System design, data flow, and component interactions
- **[minipupper-app/ROADMAP.md](minipupper-app/ROADMAP.md)** — Development phases and timeline
- **[minipupper-app/docs/PROGRESS.md](minipupper-app/docs/PROGRESS.md)** — Development log with milestones

### For Specific Features
- **[minipupper-app/docs/BARGE_IN_GUIDE.md](minipupper-app/docs/BARGE_IN_GUIDE.md)** — Barge-in implementation, tuning, and troubleshooting
- **[minipupper-app/docs/GOOGLE_CLOUD_SETUP.md](minipupper-app/docs/GOOGLE_CLOUD_SETUP.md)** — Google Cloud API setup and credentials
- **[minipupper-app/docs/OPENCLAW_INTEGRATION.md](minipupper-app/docs/OPENCLAW_INTEGRATION.md)** — OpenClaw task delegation protocol

### For Deployment & Operations
- **[minipupper-app/docs/DEPLOYMENT_GUIDE.md](minipupper-app/docs/DEPLOYMENT_GUIDE.md)** — Production deployment with systemd service
- **[docs/Pairing.md](docs/Pairing.md)** — OpenClaw integration and authentication
- **[docs/Design.md](docs/Design.md)** — Companion app architecture and design decisions

### For Testing & Development
- **[minipupper-app/docs/TESTING_PLAN.md](minipupper-app/docs/TESTING_PLAN.md)** — Unit, integration, and system test strategy

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│              USER (Voice Input/Output)              │
└────┬──────────────────────────────────────┬─────────┘
     │ ASR (speech→text)                    │ TTS (text→speech)
     ▼                                      ▲
┌──────────────────────────────────────────────────────────┐
│         MINIPUPPER OPERATOR (Voice Assistant)            │
│                                                          │
│  ┌──────────────┐  ┌──────────┐  ┌──────────────────┐   │
│  │ Audio Manager│  │    TTS   │  │ LLM Engine       │   │
│  │ (Google STT) │  │(Google)  │  │ (Gemini 1.5 +    │   │
│  └──────────────┘  └──────────┘  │ Ollama fallback) │   │
│       ▲                           └────────┬─────────┘   │
│       │ Barge-in Detection                 │              │
│       │ (interrupts TTS)                    ▼             │
│       └──────────────────────────────────────────────────┤
│                                                          │
│  ┌─────────────────────────────────────────────────┐    │
│  │ Task Queue Architecture (Inter-component IPC)   │    │
│  │  - input_text_queue (ASR → Operator)           │    │
│  │  - output_text_queue (Operator → TTS)          │    │
│  │  - barge_in_detected (Detector → Audio Manager)│    │
│  │  - movement_queue (Operator → Robot Control)   │    │
│  │  - control_queue (External → System Control)   │    │
│  └─────────────────────────────────────────────────┘    │
│                                                          │
│  ┌─────────────────────────────────────────────────┐    │
│  │ Task Protocol & OpenClaw Integration            │    │
│  │  - File-based task protocol (tasks.json)        │    │
│  │  - TaskWatcher (polls for task completions)     │    │
│  │  - TaskArchiver (maintains history)             │    │
│  │  - OpenClaw Gateway Client (task delegation)    │    │
│  └─────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────┘
                            │
                            ├─────────────────────┐
                            ▼                     ▼
              ┌──────────────────────┐  ┌──────────────┐
              │ Robot Control APIs   │  │ OpenClaw     │
              │ (Movement, sensors)  │  │ Gateway      │
              │                      │  │ (Task exec)  │
              └──────────────────────┘  └──────────────┘
```

## 🔑 Key Components

| Component | Purpose | Technology |
|-----------|---------|-----------|
| **Audio Manager** | Speech-to-text and text-to-speech | Google Cloud Speech API + TTS |
| **Barge-In Detector** | Detects user speech during robot speech | Energy-based detection + AEC |
| **LLM Engine** | AI reasoning and conversation | Gemini 1.5 Flash (Vertex AI) + Ollama fallback |
| **Task Queue** | Inter-process communication | Python `queue.Queue` (thread-safe) |
| **Task Protocol** | File-based task delegation | JSON file polling + archiving |
| **OpenClaw Client** | Integration with OpenClaw Gateway | WebSocket + REST |
| **Robot Control** | Movement and sensor APIs | Extensible module structure |

## 📊 Development Status (May 2026)

### ✅ Completed (Phase 1 & Phase 2)
- Audio pipeline (Google Cloud STT, TTS, barge-in detection)
- Gemini 1.5 Flash integration (Vertex AI)
- Queue-based worker architecture
- File-based task protocol with OpenClaw
- Task archiving and history tracking
- Configuration system (YAML + environment)
- Comprehensive documentation

### 🔄 In Progress
- Latency optimization (target <5s for task execution)
- Event-driven task watching (replacing file polling)

### ⏳ Upcoming (Phase 3+)
- Robot movement control integration
- Sensor integration (IMU, distance, battery)
- Production hardening and stability testing
- Deployment and monitoring tools

See [minipupper-app/ROADMAP.md](minipupper-app/ROADMAP.md) for the complete phase breakdown and timeline.

## 🛠️ Development Workflow

### For Contributors

1. **Understand the codebase:**
   - Read [minipupper-app/docs/ARCHITECTURE.md](minipupper-app/docs/ARCHITECTURE.md)
   - Explore the `src/` directory structure

2. **Set up your environment:**
   ```bash
   cd minipupper-app
   python3.10 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Configure your environment:**
   - Copy `config/.env.sample` to `config/.env`
   - Fill in your Google Cloud credentials
   - Adjust `config/config.yaml` as needed

4. **Run tests:**
   ```bash
   # See TESTING_PLAN.md for all test strategies
   python -m pytest scripts/test_pipeline.py
   ```

5. **Run the application:**
   ```bash
   python minipupper_operator.py
   ```

### Local Development vs. Production

- **Local/Dev:** Run directly on Pi or development machine
- **Production:** Deploy as systemd service (see [DEPLOYMENT_GUIDE.md](minipupper-app/docs/DEPLOYMENT_GUIDE.md))

## 🔐 Configuration & Credentials

### Required Google Cloud Setup
1. Create a Google Cloud project
2. Enable APIs:
   - Cloud Speech-to-Text
   - Cloud Text-to-Speech
   - Vertex AI (for Gemini)
3. Create a service account with appropriate roles
4. Download credentials JSON and configure `config/.env`

For step-by-step instructions, see [minipupper-app/docs/GOOGLE_CLOUD_SETUP.md](minipupper-app/docs/GOOGLE_CLOUD_SETUP.md).

### Optional OpenClaw Setup
If using task delegation to OpenClaw:
1. Set up OpenClaw Gateway (self-hosted or cloud)
2. Configure authentication in `config/config.yaml`
3. Enable task protocol in operator config

See [minipupper-app/docs/OPENCLAW_INTEGRATION.md](minipupper-app/docs/OPENCLAW_INTEGRATION.md).

## 🧪 Testing

The project includes three levels of testing:

- **Unit Tests** — Individual modules (audio, barge-in, LLM engine)
- **Integration Tests** — Component interactions and full conversation flows
- **System Tests** — End-to-end reliability and performance

See [minipupper-app/docs/TESTING_PLAN.md](minipupper-app/docs/TESTING_PLAN.md) for the complete test matrix and how to run tests.

## 📦 Dependencies

### Core Requirements
- `faster-whisper` — Local speech-to-text (fallback)
- `google-cloud-speech` — Google Cloud STT
- `google-cloud-texttospeech` — Google Cloud TTS
- `google-cloud-aiplatform` — Vertex AI (Gemini)
- `numpy`, `scipy` — Audio processing
- `pyyaml` — Configuration

See `minipupper-app/requirements.txt` for the full list and versions.

## 🚦 Known Limitations & Next Steps

1. **Latency** — Current task execution is 15-20s; targeting <5s
2. **Event-Driven** — Currently uses file polling; moving to event-driven architecture
3. **Robot Control** — Movement APIs need hardware testing
4. **Sensors** — IMU, distance, battery integration pending

Refer to [minipupper-app/ROADMAP.md](minipupper-app/ROADMAP.md) for detailed phase breakdown.

## 🤝 Contributing

This is an **active development project**. If you're contributing:

1. Familiarize yourself with the architecture documentation
2. Follow the code structure in `src/` (modules are well-separated)
3. Update [minipupper-app/docs/PROGRESS.md](minipupper-app/docs/PROGRESS.md) when completing work
4. Add tests for new features (see [TESTING_PLAN.md](minipupper-app/docs/TESTING_PLAN.md))
5. Keep documentation in sync with code changes

## 📞 Support & Troubleshooting

- **Audio/Microphone Issues** → [minipupper-app/docs/BARGE_IN_GUIDE.md](minipupper-app/docs/BARGE_IN_GUIDE.md)
- **Google Cloud Setup** → [minipupper-app/docs/GOOGLE_CLOUD_SETUP.md](minipupper-app/docs/GOOGLE_CLOUD_SETUP.md)
- **Deployment** → [minipupper-app/docs/DEPLOYMENT_GUIDE.md](minipupper-app/docs/DEPLOYMENT_GUIDE.md)
- **OpenClaw Integration** → [minipupper-app/docs/OPENCLAW_INTEGRATION.md](minipupper-app/docs/OPENCLAW_INTEGRATION.md)
- **Architecture Questions** → [minipupper-app/docs/ARCHITECTURE.md](minipupper-app/docs/ARCHITECTURE.md)

## 📜 License

See [reference/LICENSE](reference/LICENSE) for licensing information.

---

**Last Updated:** May 2026  
**Project Status:** Phase 2 Active (OpenClaw Integration)  
**Next Milestone:** Phase 3 (Robot Control Integration) — June 2026
