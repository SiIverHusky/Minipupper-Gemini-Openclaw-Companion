# Deployment & Operations Guide

**Last Updated:** 2026-05-09  
**Version:** 0.1 Alpha  
**Target Platform:** Minipupper (Raspberry Pi 4, Debian 11)

---

## 1. System Requirements

### Hardware
- **Robot:** Minipupper Quadruped Robot
- **Compute:** Raspberry Pi 4 (4GB minimum, 8GB recommended)
- **Storage:** 64GB microSD card (UHS-I recommended)
- **Audio:** USB microphone + speaker, or built-in audio
- **Network:** WiFi (for Tailscale mesh network)
- **Optional:** USB GPU/TPU accelerator for faster inference

### Software
- **OS:** Debian 11 or Ubuntu 22.04 (Raspberry Pi compatible)
- **Python:** 3.9 or 3.10
- **Dependencies:** See `requirements.txt`
- **Services:** Systemd (for service management)

### Network
- **Tailscale:** For secure mesh network to cloud gateway
- **Local Network:** Fallback for direct connectivity
- **Bandwidth:** 10+ Mbps recommended for TTS/ASR
- **Latency:** Should be < 100ms to cloud services (optional)

---

## 2. Installation Steps

### 2.1 Prepare Minipupper System

```bash
# SSH into Minipupper
ssh minipupper@minipupper.local
# or: ssh minipupper@192.168.1.100

# Update system packages
sudo apt update && sudo apt upgrade -y

# Install system dependencies
sudo apt install -y \
    python3.10 \
    python3.10-venv \
    python3.10-dev \
    git \
    build-essential \
    libsndfile1 \
    portaudio19-dev \
    alsa-utils \
    pulseaudio \
    curl

# Install Tailscale (if not already)
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

### 2.2 Clone Repository

```bash
# Clone the project
cd /home/minipupper
git clone https://github.com/mangdangroboticsclub/minipupper-app.git
cd minipupper-app

# Or if already cloned:
git pull origin main
```

### 2.3 Setup Python Environment

```bash
# Create virtual environment
python3.10 -m venv venv
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip setuptools wheel

# Install dependencies
pip install -r requirements.txt

# Verify installation
python -c "import faster_whisper; print('✓ faster-whisper')"
python -c "import google.cloud.texttospeech; print('✓ Google Cloud TTS')"
```

### 2.4 Configure Environment

```bash
# Copy environment template
cp config/.env.sample config/.env

# Edit configuration
nano config/.env

# Required settings:
#   GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
#   GOOGLE_CLOUD_PROJECT_ID=your-project-id
#   AUDIO_DEVICE_INDEX=-1  (or specific device)
#   DEBUG=false (for production)

# Make config directory
mkdir -p logs

# Test configuration
python -c "from minipupper_operator import MinipupperOperator; print('✓ Config OK')"
```

### 2.5 Configure Google Cloud (if using TTS/ASR APIs)

```bash
# Create service account key on Google Cloud Console:
# 1. Go to: https://console.cloud.google.com/
# 2. Create service account with TTS + Speech API permissions
# 3. Download JSON key
# 4. Copy to Minipupper

scp /local/path/to/key.json minipupper@minipupper.local:/home/minipupper/minipupper-app/config/gcloud_key.json

# On Minipupper, set in .env:
# GOOGLE_APPLICATION_CREDENTIALS=/home/minipupper/minipupper-app/config/gcloud_key.json
```

### 2.6 Test Installation

```bash
# Run operator in foreground (for debugging)
source venv/bin/activate
python minipupper_operator.py

# Expected output:
# 2026-05-09 14:30:15,123 - __main__ - INFO - Minipupper Operator initialized
# 2026-05-09 14:30:15,456 - __main__ - INFO - Minipupper Operator started

# Press Ctrl+C to stop
```

---

## 3. Service Installation (Systemd)

### 3.1 Create Service File

```bash
# Create systemd service
sudo nano /etc/systemd/system/minipupper-operator.service
```

**Content:**
```ini
[Unit]
Description=Minipupper Operator - Voice AI Assistant
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=minipupper
WorkingDirectory=/home/minipupper/minipupper-app
Environment="PATH=/home/minipupper/minipupper-app/venv/bin"
ExecStart=/home/minipupper/minipupper-app/venv/bin/python minipupper_operator.py
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=minipupper-operator

# Resource limits
MemoryLimit=2G
CPUQuota=80%

# Logging
StandardOutput=append:/home/minipupper/minipupper-app/logs/operator.log

[Install]
WantedBy=multi-user.target
```

### 3.2 Enable & Start Service

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable service (start on boot)
sudo systemctl enable minipupper-operator.service

# Start service
sudo systemctl start minipupper-operator.service

# Check status
sudo systemctl status minipupper-operator.service

# View logs
journalctl -u minipupper-operator.service -f  # Follow logs
journalctl -u minipupper-operator.service --since "1 hour ago"

# Stop service
sudo systemctl stop minipupper-operator.service

# Restart service
sudo systemctl restart minipupper-operator.service
```

---

## 4. Configuration Management

### 4.1 Audio Device Selection

```bash
# List audio devices
python -c "import sounddevice; print(sounddevice.query_devices())"

# Output example:
#   0: Micro: USB Audio [plughw:1,0]
#   1: Speaker: USB Audio [plughw:1,1]
#   2: HDMI [alsa: ...] (default)

# Update config/.env
AUDIO_DEVICE_INDEX=0  # Use first device for input
```

### 4.2 Barge-in Tuning

**Environment-Specific Thresholds:**

```yaml
# Quiet environment (home/office)
audio:
  barge_in:
    min_energy_threshold: 300

# Normal environment (standard robot operation)
audio:
  barge_in:
    min_energy_threshold: 500

# Noisy environment (outdoor/factory)
audio:
  barge_in:
    min_energy_threshold: 800
```

**Fine-tuning Process:**
```bash
# 1. Run detector to measure baseline noise
python -m src.audio.barge_in_detector

# 2. Observe noise energy levels
# 3. Adjust threshold to 3-5x noise level
# 4. Test by speaking during robot speech
```

### 4.3 LLM Model Selection

**Local Models (Ollama):**
```bash
# Install Ollama: https://ollama.ai/

# Pull model on Minipupper
ollama pull mistral:7b-instruct

# Configure in config.yaml
operator:
  llm_provider: "ollama"
  ollama_model: "mistral:7b-instruct"
  ollama_base_url: "http://localhost:11434"
```

**Cloud Models (Google Vertex AI):**
```bash
# Configure in config.yaml
operator:
  llm_provider: "google"
  google_model: "gemini-pro"
  temperature: 0.7
```

---

## 5. Monitoring & Logging

### 5.1 Log Files

```bash
# Main application log
tail -f logs/minipupper_operator.log

# Systemd journal
journalctl -u minipupper-operator.service -f

# Python traceback (if crash)
grep -i error logs/minipupper_operator.log
```

### 5.2 Logging Configuration

**File:** `config/config.yaml`

```yaml
logging:
  file: "logs/minipupper_operator.log"
  max_file_size_mb: 50  # Rotate at 50MB
  backup_count: 5       # Keep 5 backups (250MB total)
  console_output: true  # Also print to console
```

### 5.3 Health Checks

```bash
# Check if service is running
systemctl is-active minipupper-operator.service

# Monitor resource usage
ps aux | grep minipupper_operator

# Check memory usage
free -h
ps -o rss= -p $(pgrep -f minipupper_operator)

# Check disk space
df -h /home/minipupper/minipupper-app

# Monitor audio devices
arecord -l  # List input devices
aplay -l    # List output devices
```

---

## 6. Network Configuration

### 6.1 Tailscale Setup

```bash
# Install (if not already done)
curl -fsSL https://tailscale.com/install.sh | sh

# Authenticate with Tailscale account
sudo tailscale up

# Get Minipupper IP on Tailscale network
tailscale ip -4

# Check connection status
tailscale status
```

### 6.2 Local Network Access

```bash
# SSH from local network
ssh minipupper@minipupper.local
ssh minipupper@192.168.1.100

# Or from cloud (via Tailscale)
tailscale list  # Find Minipupper IP
ssh minipupper@100.x.x.x
```

### 6.3 Cloud Gateway Integration

**Configuration:** `config/config.yaml`

```yaml
network:
  tailscale_enabled: true
  local_network: true
  default_port: 8888
  
  cloud_gateway:
    enabled: true
    endpoint: "https://cloud-gateway.example.com"
    timeout_seconds: 30
```

---

## 7. Maintenance & Updates

### 7.1 Regular Maintenance

```bash
# Weekly: Check logs for errors
journalctl -u minipupper-operator.service --since "7 days ago" | grep -i error

# Monthly: Clean old logs
find logs/ -name "*.log.*" -mtime +30 -delete

# Monthly: Update packages
pip install --upgrade pip setuptools wheel
pip list --outdated

# Quarterly: Update system packages
sudo apt update && sudo apt upgrade -y
```

### 7.2 Software Updates

```bash
# Pull latest code
cd /home/minipupper/minipupper-app
git pull origin main

# Update dependencies
source venv/bin/activate
pip install -r requirements.txt --upgrade

# Restart service
sudo systemctl restart minipupper-operator.service

# Verify
systemctl status minipupper-operator.service
```

### 7.3 Backup & Recovery

```bash
# Backup configuration
tar -czf ~/backup_minipupper_config_$(date +%Y%m%d).tar.gz \
  /home/minipupper/minipupper-app/config/

# Backup logs
tar -czf ~/backup_minipupper_logs_$(date +%Y%m%d).tar.gz \
  /home/minipupper/minipupper-app/logs/

# Restore from backup
tar -xzf backup_minipupper_config_20260509.tar.gz -C /
```

---

## 8. Troubleshooting

### Problem: Service Won't Start

```bash
# Check service status
systemctl status minipupper-operator.service

# Check logs
journalctl -u minipupper-operator.service -n 50

# Test manually (debug)
source /home/minipupper/minipupper-app/venv/bin/activate
cd /home/minipupper/minipupper-app
python minipupper_operator.py

# If error about GOOGLE_APPLICATION_CREDENTIALS:
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json
python minipupper_operator.py
```

### Problem: No Audio Input

```bash
# Check audio devices
arecord -l
aplay -l

# Test recording
arecord -d 3 -f cd /tmp/test.wav

# Check microphone in Python
python -c "
import sounddevice as sd
import numpy as np
stream = sd.InputStream()
with stream:
    data, _ = stream.read(16000)
    print(f'Energy: {np.sqrt(np.mean(data**2)):.1f}')
"

# Check .env AUDIO_DEVICE_INDEX
grep AUDIO_DEVICE_INDEX config/.env
```

### Problem: High Latency / Slow Responses

```bash
# Check system load
top -bn1 | head -20

# Check if TLS certificates are fresh
date
curl -I https://cloud-gateway.example.com

# Monitor network
iftop  # If installed
netstat -an | grep ESTABLISHED

# Check Tailscale connection
tailscale status
ping 100.x.x.x  # Ping via Tailscale
```

### Problem: Memory Leak / High RAM Usage

```bash
# Monitor memory over time
watch -n 5 'free -h && ps aux | grep minipupper'

# Get memory dump
ps -o pid,vsz,rss -p $(pgrep -f minipupper_operator)

# Restart service
sudo systemctl restart minipupper-operator.service

# Check for zombie processes
ps aux | grep defunct
```

---

## 9. Performance Tuning

### 9.1 CPU Optimization

```bash
# Reduce logging overhead
sed -i 's/log_level: "INFO"/log_level: "WARNING"/' config/config.yaml

# Use quantized models
# config.yaml
audio:
  asr:
    compute_type: "int8"  # Was float32

# Reduce model size
audio:
  asr:
    model: "tiny"  # Was "base" (fast, lower quality)
```

### 9.2 Memory Optimization

```yaml
# Reduce context length
operator:
  max_context_length: 2048  # Was 8192

# Smaller batch sizes
audio:
  asr:
    chunk_size: 2048  # Was 4096
```

### 9.3 Network Optimization

```bash
# Check network latency
ping -c 5 cloud-gateway.example.com

# If latency is high, enable local mode only
# config/.env
CLOUD_GATEWAY_ENABLED=false

# Or increase timeout
CLOUD_TIMEOUT_SECONDS=60
```

---

## 10. Disaster Recovery

### 10.1 Service Crashed

```bash
# Restart immediately
sudo systemctl restart minipupper-operator.service

# If repeatedly crashing, check logs first
journalctl -u minipupper-operator.service -n 100 --output=short-precise

# Disable service temporarily
sudo systemctl stop minipupper-operator.service
sudo systemctl disable minipupper-operator.service
```

### 10.2 Storage Full

```bash
# Check disk space
df -h /home/minipupper

# Identify large files
du -sh /home/minipupper/minipupper-app/*

# Clean logs
rm -rf logs/*.log.*  # Remove archived logs
echo "" > logs/minipupper_operator.log  # Clear current log

# Clean cache
rm -rf ~/.cache
```

### 10.3 Network Disconnected

**Minipupper will continue operating locally** with these caveats:
- Cloud API calls will fail (fallback to local responses)
- No remote monitoring/updates
- Tailscale will show as offline

```bash
# Verify local operation
python minipupper_operator.py  # Should still work

# Check Tailscale connection
tailscale status
tailscale down  # Disconnect
tailscale up    # Reconnect
```

---

## 11. Deployment Checklist

Before going live, verify:

- [ ] System requirements met (RAM, storage, network)
- [ ] Dependencies installed and tested
- [ ] Configuration files filled in (.env)
- [ ] Google Cloud credentials available (if using cloud services)
- [ ] Audio devices detected and working
- [ ] Tailscale connected
- [ ] Service installs and starts cleanly
- [ ] Logs are readable and rotated
- [ ] Barge-in thresholds tuned for environment
- [ ] Health checks pass (memory, CPU, disk)
- [ ] Backup strategy in place

---

## 12. Rollback Plan

If deployment fails:

```bash
# Stop current service
sudo systemctl stop minipupper-operator.service

# Restore from backup
cd /home/minipupper/minipupper-app
git reset --hard HEAD~1  # Revert to previous commit

# Or checkout specific tag
git checkout v0.0.1

# Restart service
sudo systemctl start minipupper-operator.service
```

---

**Last Updated:** 2026-05-09  
**Next Review:** 2026-05-20 (after initial deployment)
