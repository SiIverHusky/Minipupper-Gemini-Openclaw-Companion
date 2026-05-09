"""Quick Start Guide for Minipupper Operator"""

# Quick Start - 5 Minutes to Running

## 1. Install (2 minutes)

```bash
cd /home/minipupper
git clone https://github.com/mangdangroboticsclub/minipupper-app.git
cd minipupper-app

python3.10 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 2. Configure (2 minutes)

```bash
cp config/.env.sample config/.env
nano config/.env

# Fill in:
# GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json
# GOOGLE_CLOUD_PROJECT_ID=your-project-id
# DEBUG=false
```

## 3. Run (1 minute)

```bash
python minipupper_operator.py

# Expected output:
# 2026-05-09 14:30:15 - minipupper_operator - INFO - Minipupper Operator started
# Listening for user input...
```

---

## Test Barge-in Feature

In a separate terminal:

```bash
cd /home/minipupper/minipupper-app
source venv/bin/activate

# Run the barge-in detector
python -m src.audio.barge_in_detector

# Output: "Listening for barge-in... Press Ctrl+C to stop"
# Try speaking loudly - you should see:
# Speech detected (energy: 650.5)
```

---

## Next: Read the Documentation

1. **ARCHITECTURE.md** - Understand the system design
2. **BARGE_IN_GUIDE.md** - Learn about the barge-in feature
3. **TESTING_PLAN.md** - Plan your testing approach
4. **DEPLOYMENT_GUIDE.md** - Deploy to production

All files in the `docs/` folder are dated and designed for human-side development.

---

## Troubleshooting

**Service won't start?**
```bash
# Test manually
python minipupper_operator.py
# You'll see the actual error

# Check dependencies
pip list | grep -E "faster-whisper|google"
```

**No audio input?**
```bash
# List audio devices
arecord -l

# Set correct device in config/.env
AUDIO_DEVICE_INDEX=0
```

**Barge-in too sensitive?**
```yaml
# Edit config/config.yaml
barge_in:
  min_energy_threshold: 800  # Increase from 500
```

---

## Key Files

| File | Purpose |
|------|---------|
| `minipupper_operator.py` | Main application |
| `config/config.yaml` | Settings (audio, barge-in) |
| `config/.env` | Credentials & device selection |
| `src/audio/` | Speech I/O and barge-in |
| `src/core/task_queue.py` | Inter-component communication |
| `docs/` | Detailed documentation (all dated) |

---

## System Requirements

- **Robot:** Minipupper (Raspberry Pi 4, 4GB RAM minimum)
- **OS:** Debian 11 / Ubuntu 22.04
- **Python:** 3.9+
- **Audio:** USB microphone + speaker
- **Network:** Tailscale (optional but recommended)

---

**Current Status:** Alpha 0.1 - Early Development  
**Last Updated:** 2026-05-09

For detailed information, see the documentation in the `docs/` folder.
