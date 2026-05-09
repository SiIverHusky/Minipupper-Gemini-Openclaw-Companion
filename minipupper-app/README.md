# Minipupper Operator - Voice-First AI Assistant

**Status:** Audio Pipeline Complete (Phase 1 Done)  
**Last Updated:** 2026-05-09  
**Platform:** Minipupper Robot (Raspberry Pi 4, Debian 11)

---

## Overview

Minipupper Operator is a **standalone, voice-first conversational AI agent** running directly on your Minipupper robot. It provides robust autonomous capabilities with **barge-in support** (user can interrupt the robot's speech at any time).

### Key Features
- 🎤 **Speech Recognition** - Google Cloud Speech-to-Text (95%+ accuracy)
- 🔊 **Text-to-Speech** - Google Cloud TTS with natural voices
- 🤖 **AI Reasoning** - Gemini 1.5 Flash via Vertex AI (fast, capable)
- ⚡ **Barge-in Ready** - User interrupts robot speech instantly
- 🌐 **Autonomous Operation** - No OpenClaw dependency
- 🔌 **Tailscale Connected** - Secure mesh network to cloud
- 📊 **Queue-Based Architecture** - Scalable, decoupled components

### Models in Use
| Component | Model | Provider |
|-----------|-------|----------|
| **Speech-to-Text** | Google Cloud Speech-to-Text API | Google Cloud |
| **AI Reasoning** | Gemini 1.5 Flash | Google Vertex AI |
| **Text-to-Speech** | Google Cloud TTS | Google Cloud |
| **Fallback LLM** | Mistral (local) | Ollama (optional) |

---

## Quick Start (5 minutes)

### Prerequisites
- Minipupper robot with Raspberry Pi 4 (4GB+ RAM)
- Microphone + speakers connected
- Python 3.9+ installed
- Google Cloud account with credentials

### Installation

```bash
# 1. Clone repository
cd /home/minipupper
git clone https://github.com/mangdangroboticsclub/minipupper-app.git
cd minipupper-app

# 2. Create Python environment
python3.10 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up Google Cloud credentials
cp config/.env.sample config/.env
# Edit config/.env and add:
#   GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
#   GOOGLE_CLOUD_PROJECT_ID=your-project-id

# 5. Run!
python minipupper_operator.py
```

### Google Cloud Setup

See [docs/GOOGLE_CLOUD_SETUP.md](docs/GOOGLE_CLOUD_SETUP.md) for:
- Creating Google Cloud project
- Enabling Speech-to-Text, TTS, and Vertex AI APIs
- Setting up service account credentials
- Cost estimation

### Test Barge-in Locally

```bash
# Test speech detection
python -m src.audio.barge_in_detector

# Output: "Listening for barge-in... Press Ctrl+C to stop"
# Try speaking while this is running!
```

---

## Architecture

```
┌─────────────────────────────────────────────┐
│       Minipupper Operator                   │
├─────────────────────────────────────────────┤
│                                             │
│  Audio Layer (ASR, TTS, Barge-in)          │
│  ├─ Google Cloud Speech-to-Text (primary) │
│  ├─ Whisper (fallback)                    │
│  └─ Google Cloud TTS                      │
│                                             │
│  AI Reasoning (LLM)                         │
│  ├─ Gemini 1.5 Flash (primary)            │
│  ├─ Ollama (local fallback)                │
│  └─ Template responses (fallback)          │
│                                             │
│  Core Logic (Operator, Workers)             │
│  └─ Queue-based IPC                        │
│                                             │
│  Robot Control (Movement, Sensors)          │
│  └─ Movement API (to be integrated)         │
│                                             │
└─────────────────────────────────────────────┘
         │
         └─► Tailscale Network
         └─► Optional: Cloud Gateway
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed diagrams and component descriptions.

---

## Configuration

### Main Settings (config.yaml)

```yaml
# Audio engines - Google Cloud by default
audio:
  asr:
    engine: "google"          # Google Cloud Speech-to-Text
    # Fallback: "whisper"     # Local Whisper model
  
  tts:
    engine: "google"          # Google Cloud TTS
    voice: "en-US-Neural2-A"  # Natural sounding voice

# AI Reasoning - Gemini by default
operator:
  llm_provider: "gemini"                    # Gemini Vertex AI
  llm_model: "gemini-1.5-flash"            # Fast, capable model
  # Alternatives: "ollama" (local), "fallback" (template)

# Barge-in tuning
barge_in:
  enabled: true
  min_energy_threshold: 500  # Adjust for your environment
  detection_timeout_ms: 500
```

See [config/config.yaml](config/config.yaml) for all options.

---

## Barge-in Feature

**What it does:** User can interrupt the robot's speech by speaking over it.

**How to test:**
```bash
# Robot speaks a response while listening for interruption
# User speaks → Robot detects speech → TTS stops immediately
# User input is processed next
```

**Configuration:**
- Adjust `barge_in.min_energy_threshold` based on ambient noise
- See [docs/BARGE_IN_GUIDE.md](docs/BARGE_IN_GUIDE.md) for details

---

## Development

### Project Structure

```
minipupper-app/
├── src/
│   ├── core/              # Core application logic
│   │   ├── task_queue.py  # Inter-component communication
│   │   └── llm_engine.py  # LLM provider abstraction (Gemini, Ollama, etc.)
│   ├── audio/             # Audio I/O
│   │   ├── audio_manager.py         # ASR/TTS with barge-in
│   │   └── barge_in_detector.py    # Speech detection
│   └── robot/             # Robot-specific control
│       └── movement_api.py (TODO)
├── config/
│   ├── config.yaml        # Main configuration
│   └── .env.sample        # Environment variables
├── docs/
│   ├── PROGRESS.md              # Development log with dates
│   ├── ARCHITECTURE.md          # System design
│   ├── BARGE_IN_GUIDE.md        # Barge-in documentation
│   ├── TESTING_PLAN.md          # Test strategy
│   ├── DEPLOYMENT_GUIDE.md      # Operations guide
│   └── GOOGLE_CLOUD_SETUP.md    # Google Cloud setup (NEW)
├── tests/                 # Unit & integration tests (TODO)
├── logs/                  # Application logs
├── requirements.txt       # Python dependencies
├── minipupper_operator.py # Main entry point
└── README.md              # This file
```

### Next Steps for Developers

1. **Test Gemini LLM** - Validate responses with real API (Week 1)
2. **Implement ASR Streaming** - Lower latency speech recognition (Week 1)
3. **Movement Control** - Robot command mapping (Week 2)
4. **Integration Testing** - Full system validation (Week 3)

See [ROADMAP.md](ROADMAP.md) for detailed development timeline.

---

## Documentation

All development is tracked with **dated companion documents**:

| Document | Purpose | Updated |
|----------|---------|---------|
| [PROGRESS.md](docs/PROGRESS.md) | Development log & milestones | 2026-05-09 |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design & data flow | 2026-05-09 |
| [BARGE_IN_GUIDE.md](docs/BARGE_IN_GUIDE.md) | Barge-in implementation details | 2026-05-09 |
| [TESTING_PLAN.md](docs/TESTING_PLAN.md) | Test strategy & checklist | 2026-05-09 |
| [DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md) | Installation & operations | 2026-05-09 |
| [GOOGLE_CLOUD_SETUP.md](docs/GOOGLE_CLOUD_SETUP.md) | Google Cloud credential setup | 2026-05-09 |

---

## Deployment

### Local Testing
```bash
python minipupper_operator.py
```

### Systemd Service (Production)
```bash
# Install service
sudo cp docs/minipupper-operator.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable minipupper-operator.service
sudo systemctl start minipupper-operator.service

# View logs
journalctl -u minipupper-operator.service -f
```

See [DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md) for complete setup instructions.

---

## Testing

### Run Tests
```bash
# Unit tests (Phase 1 - TODO)
pytest tests/unit/ -v

# Integration tests (Phase 2 - TODO)
pytest tests/integration/ -v

# Barge-in detector test
python -m src.audio.barge_in_detector
```

See [TESTING_PLAN.md](docs/TESTING_PLAN.md) for complete test strategy.

---

## Troubleshooting

### Google Cloud Credentials Not Found
```bash
# Verify path
echo $GOOGLE_APPLICATION_CREDENTIALS

# Test credentials
gcloud auth application-default print-access-token

# Set if needed
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json
```

### Barge-in Not Working
```bash
# Increase energy threshold if too sensitive
barge_in:
  min_energy_threshold: 800

# Test detector separately
python -m src.audio.barge_in_detector
```

### Service Won't Start
```bash
# Check logs
journalctl -u minipupper-operator.service -n 50

# Test manually
source venv/bin/activate
python minipupper_operator.py
```

See [DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md#8-troubleshooting) for more solutions.

---

## Configuration Files

### config.yaml
Main application configuration (audio, barge-in, operator, LLM settings)

### .env
Environment variables (Google Cloud credentials, device selection, etc.)
```bash
cp config/.env.sample config/.env
# Edit with your values
```

See [GOOGLE_CLOUD_SETUP.md](docs/GOOGLE_CLOUD_SETUP.md) for setup instructions.

---

## Network

### Tailscale Setup
```bash
# Install and authenticate
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up

# Get IP on Tailscale network
tailscale ip -4
```

App operates locally even if cloud connection is down.

---

## Performance Targets

| Metric | Target |
|--------|--------|
| Speech→Text (ASR) | < 2 seconds |
| Text→Response (LLM) | 2-5 seconds (Gemini) |
| Response→Audio (TTS) | < 1 second |
| Barge-in Latency | < 500ms |
| **Total Conversation Latency** | **< 8 seconds** |

---

## Requirements

### Hardware
- Raspberry Pi 4 (4GB minimum, 8GB recommended)
- 64GB microSD (UHS-I recommended)
- USB microphone + speaker (or built-in audio)
- Minipupper Quadruped Robot

### Software
- Python 3.9+
- Debian 11 / Ubuntu 22.04
- All dependencies in `requirements.txt`

### Google Cloud
- Active Google Cloud account
- Service account with API permissions
- APIs enabled: Speech-to-Text, TTS, Vertex AI

---

## Roadmap

**Phase 1 (May 2026)** - Audio & Barge-in ✅ COMPLETE
- ✅ Barge-in detection framework
- ✅ Google Cloud Speech-to-Text integration
- ✅ Gemini LLM integration via Vertex AI

**Phase 2 (June 2026)** - Operator Logic
- ⏳ LLM response generation testing
- ⏳ Conversation context management
- ⏳ Integration testing

**Phase 3 (July 2026)** - Robot Control
- ⏳ Movement command mapping
- ⏳ Safety validation
- ⏳ Hardware integration

**Phase 4 (Aug 2026)** - Production
- ⏳ Performance tuning
- ⏳ Stress testing
- ⏳ Beta release

See [ROADMAP.md](ROADMAP.md) for detailed milestone dates.

---

## Contributing

Development follows the [PROGRESS.md](docs/PROGRESS.md) timeline. Each developer should:

1. Check dated milestones before starting work
2. Update PROGRESS.md with your progress
3. Follow the queue-based architecture pattern
4. Add tests for new features
5. Update documentation with dates

---

## License

See [LICENSE](../LICENSE) file.

---

## Support

- **Documentation:** See [docs/](docs/) folder
- **Google Cloud Setup:** [docs/GOOGLE_CLOUD_SETUP.md](docs/GOOGLE_CLOUD_SETUP.md)
- **Troubleshooting:** [DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md#8-troubleshooting)
- **Issues:** Check [PROGRESS.md](docs/PROGRESS.md) for known issues

---

**Status:** Phase 1 Complete - Audio Pipeline Ready  
**Last Updated:** 2026-05-09  
**Next Phase:** Operator Logic Testing


---

## Quick Start (5 minutes)

### Prerequisites
- Minipupper robot with Raspberry Pi 4 (4GB+ RAM)
- Microphone + speakers connected
- Python 3.9+ installed
- Internet connection (for model downloads)

### Installation

```bash
# 1. Clone repository
cd /home/minipupper
git clone https://github.com/mangdangroboticsclub/minipupper-app.git
cd minipupper-app

# 2. Create Python environment
python3.10 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp config/.env.sample config/.env
# Edit config/.env with your settings

# 5. Run!
python minipupper_operator.py
```

### Test Barge-in Locally

```bash
# Test speech detection
python -m src.audio.barge_in_detector

# Output: "Listening for barge-in... Press Ctrl+C to stop"
# Try speaking while this is running!
```

---

## Architecture

```
┌─────────────────────────────────────────────┐
│           Minipupper Operator               │
├─────────────────────────────────────────────┤
│                                             │
│  Audio Layer (ASR, TTS, Barge-in)          │
│  Core Logic (Operator, Workers)             │
│  Robot Control (Movement, Sensors)          │
│                                             │
│  All powered by thread-safe queues          │
│                                             │
└─────────────────────────────────────────────┘
         │
         └─► Tailscale Network
         └─► Optional: Cloud Gateway
```

See [ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed diagrams and component descriptions.

---

## Configuration

### Main Settings (config.yaml)

```yaml
# Audio engines
audio:
  asr:
    engine: "faster_whisper"
    model: "base"
    device: "cpu"
  
  tts:
    engine: "google"
    voice: "en-US-Neural2-A"

# Barge-in tuning
barge_in:
  enabled: true
  min_energy_threshold: 500  # Adjust for your environment
  detection_timeout_ms: 500

# Operator settings
operator:
  role: "minipupper_autonomous"
  max_context_length: 8192
```

See [config/config.yaml](config/config.yaml) for all options.

---

## Barge-in Feature

**What it does:** User can interrupt the robot's speech by speaking over it.

**How to test:**
```bash
# Robot speaks a response while listening for interruption
# User speaks → Robot detects speech → TTS stops immediately
# User input is processed next
```

**Configuration:**
- Adjust `barge_in.min_energy_threshold` based on ambient noise
- See [BARGE_IN_GUIDE.md](docs/BARGE_IN_GUIDE.md) for details

---

## Development

### Project Structure

```
minipupper-app/
├── src/
│   ├── core/              # Core application logic
│   │   └── task_queue.py  # Inter-component communication
│   ├── audio/             # Audio I/O
│   │   ├── audio_manager.py
│   │   └── barge_in_detector.py
│   └── robot/             # Robot-specific control
│       └── movement_api.py (TODO)
├── config/
│   ├── config.yaml        # Main configuration
│   └── .env.sample        # Environment variables
├── docs/
│   ├── PROGRESS.md        # Development log with dates
│   ├── ARCHITECTURE.md    # System design
│   ├── BARGE_IN_GUIDE.md  # Barge-in documentation
│   ├── TESTING_PLAN.md    # Test strategy
│   └── DEPLOYMENT_GUIDE.md # Operations guide
├── tests/                 # Unit & integration tests (TODO)
├── logs/                  # Application logs
├── requirements.txt       # Python dependencies
├── minipupper_operator.py # Main entry point
└── README.md              # This file
```

### Next Steps for Developers

1. **Audio Pipeline** - Complete ASR/TTS integration (Week 1)
2. **Operator Logic** - Implement LLM-based responses (Week 2)
3. **Movement Control** - Robot command mapping (Week 3)
4. **Integration Testing** - Full system validation (Week 4)

See [PROGRESS.md](docs/PROGRESS.md) for detailed development timeline.

---

## Documentation

All development is tracked with **dated companion documents**:

| Document | Purpose | Updated |
|----------|---------|---------|
| [PROGRESS.md](docs/PROGRESS.md) | Development log & milestones | 2026-05-09 |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design & data flow | 2026-05-09 |
| [BARGE_IN_GUIDE.md](docs/BARGE_IN_GUIDE.md) | Barge-in implementation details | 2026-05-09 |
| [TESTING_PLAN.md](docs/TESTING_PLAN.md) | Test strategy & checklist | 2026-05-09 |
| [DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md) | Installation & operations | 2026-05-09 |

---

## Deployment

### Local Testing
```bash
python minipupper_operator.py
```

### Systemd Service (Production)
```bash
# Install service
sudo cp docs/minipupper-operator.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable minipupper-operator.service
sudo systemctl start minipupper-operator.service

# View logs
journalctl -u minipupper-operator.service -f
```

See [DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md) for complete setup instructions.

---

## Testing

### Run Tests
```bash
# Unit tests (Phase 1 - TODO)
pytest tests/unit/ -v

# Integration tests (Phase 2 - TODO)
pytest tests/integration/ -v

# Barge-in detector test
python -m src.audio.barge_in_detector
```

See [TESTING_PLAN.md](docs/TESTING_PLAN.md) for complete test strategy.

---

## Troubleshooting

### No Audio Input
```bash
# List devices
arecord -l

# Test recording
arecord -d 3 -f cd /tmp/test.wav

# Set correct device in config/.env
AUDIO_DEVICE_INDEX=0
```

### Barge-in Not Working
```bash
# Increase energy threshold if too sensitive
barge_in:
  min_energy_threshold: 800

# Test detector separately
python -m src.audio.barge_in_detector
```

### Service Won't Start
```bash
# Check logs
journalctl -u minipupper-operator.service -n 50

# Test manually
source venv/bin/activate
python minipupper_operator.py
```

See [DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md#8-troubleshooting) for more solutions.

---

## Configuration Files

### config.yaml
Main application configuration (audio, barge-in, operator settings)

### .env
Environment variables (credentials, device selection, debugging)
```bash
cp config/.env.sample config/.env
# Edit with your values
```

---

## Network

### Tailscale Setup
```bash
# Install and authenticate
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up

# Get IP on Tailscale network
tailscale ip -4
```

App operates locally even if cloud connection is down.

---

## Performance Targets

| Metric | Target |
|--------|--------|
| Speech→Text (ASR) | < 2 seconds |
| Text→Response (LLM) | < 5 seconds |
| Response→Audio (TTS) | < 1 second |
| Barge-in Latency | < 500ms |
| **Total Conversation Latency** | **< 8 seconds** |

---

## Requirements

### Hardware
- Raspberry Pi 4 (4GB minimum, 8GB recommended)
- 64GB microSD (UHS-I recommended)
- USB microphone + speaker (or built-in audio)
- Minipupper Quadruped Robot

### Software
- Python 3.9+
- Debian 11 / Ubuntu 22.04
- All dependencies in `requirements.txt`

---

## Roadmap

**Phase 1 (May 2026)** - Audio & Barge-in
- ✅ Barge-in detection framework
- ⏳ ASR/TTS integration
- ⏳ End-to-end testing

**Phase 2 (June 2026)** - Operator Logic
- ⏳ LLM response generation
- ⏳ Conversation context management
- ⏳ Integration testing

**Phase 3 (July 2026)** - Robot Control
- ⏳ Movement command mapping
- ⏳ Safety validation
- ⏳ Hardware integration

**Phase 4 (Aug 2026)** - Production
- ⏳ Performance tuning
- ⏳ Stress testing
- ⏳ Beta release

See [PROGRESS.md](docs/PROGRESS.md) for detailed milestone dates.

---

## Contributing

Development follows the [PROGRESS.md](docs/PROGRESS.md) timeline. Each developer should:

1. Check dated milestones before starting work
2. Update PROGRESS.md with your progress
3. Follow the queue-based architecture pattern
4. Add tests for new features
5. Update documentation with dates

---

## License

See [LICENSE](../LICENSE) file.

---

## Support

- **Documentation:** See [docs/](docs/) folder
- **Issues:** Check [PROGRESS.md](docs/PROGRESS.md) for known issues
- **Troubleshooting:** [DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md#8-troubleshooting)

---

**Status:** Early Development (Alpha 0.1)  
**Last Updated:** 2026-05-09  
**Next Review:** 2026-05-15
