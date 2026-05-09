# Google Cloud & Gemini Integration Guide

**Last Updated:** 2026-05-09  
**Status:** Implementation Complete  
**Models Used:** Google Cloud Speech-to-Text + Gemini 1.5 Flash via Vertex AI

---

## Overview

The Minipupper Operator now uses **Google Cloud services** for speech and AI:

| Component | Service | Benefits |
|-----------|---------|----------|
| **Speech-to-Text (ASR)** | Google Cloud Speech-to-Text | 95%+ accuracy, multiple languages, real-time streaming |
| **Text-to-Speech (TTS)** | Google Cloud TTS | Natural voices, 39 languages, multiple voice options |
| **LLM / Reasoning** | Gemini 1.5 Flash via Vertex AI | Fast responses (2-5s), multimodal, state-of-the-art |

---

## Setup Instructions

### 1. Create Google Cloud Project

```bash
# Visit Google Cloud Console
https://console.cloud.google.com

# Create new project or select existing one
# Note the Project ID (e.g., "my-minipupper-123")
```

### 2. Enable Required APIs

```bash
# In Google Cloud Console, enable:
# 1. Cloud Speech-to-Text API
# 2. Cloud Text-to-Speech API
# 3. Vertex AI API
# 4. Cloud Logging API (optional, for monitoring)

# Or via gcloud CLI:
gcloud services enable \
    speech.googleapis.com \
    texttospeech.googleapis.com \
    aiplatform.googleapis.com
```

### 3. Create Service Account

```bash
# Option A: Via Google Cloud Console
# 1. Go to: IAM & Admin → Service Accounts
# 2. Click "Create Service Account"
# 3. Name: "minipupper-operator"
# 4. Grant these roles:
#    - Cloud Speech-to-Text Client
#    - Cloud Text-to-Speech Client
#    - Vertex AI User
# 5. Create key → Download as JSON

# Option B: Via gcloud CLI
gcloud iam service-accounts create minipupper-operator \
    --display-name="Minipupper Operator"

gcloud projects add-iam-policy-binding <PROJECT_ID> \
    --member="serviceAccount:minipupper-operator@<PROJECT_ID>.iam.gserviceaccount.com" \
    --role="roles/speech.client"

gcloud projects add-iam-policy-binding <PROJECT_ID> \
    --member="serviceAccount:minipupper-operator@<PROJECT_ID>.iam.gserviceaccount.com" \
    --role="roles/texttospeech.client"

gcloud projects add-iam-policy-binding <PROJECT_ID> \
    --member="serviceAccount:minipupper-operator@<PROJECT_ID>.iam.gserviceaccount.com" \
    --role="roles/aiplatform.user"

# Create and download key
gcloud iam service-accounts keys create ~/minipupper-key.json \
    --iam-account=minipupper-operator@<PROJECT_ID>.iam.gserviceaccount.com
```

### 4. Configure Minipupper

```bash
# Copy the JSON key to Minipupper
scp ~/minipupper-key.json minipupper@minipupper.local:/home/minipupper/minipupper-app/config/gcloud_key.json

# Set up .env file
cd /home/minipupper/minipupper-app
cp config/.env.sample config/.env

# Edit config/.env
nano config/.env

# Set these values:
GOOGLE_APPLICATION_CREDENTIALS=/home/minipupper/minipupper-app/config/gcloud_key.json
GOOGLE_CLOUD_PROJECT_ID=your-actual-project-id
LLM_PROVIDER=gemini
LLM_MODEL=gemini-1.5-flash
ASR_ENGINE=google
```

### 5. Verify Setup

```bash
# Test Google Cloud credentials
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/gcloud_key.json
python -c "from google.cloud import speech; print('✓ Speech API OK')"
python -c "from google.cloud import texttospeech; print('✓ TTS API OK')"

# Test Vertex AI / Gemini
python -c "from langchain_google_vertexai import ChatVertexAI; print('✓ Vertex AI OK')"

# Run operator
python minipupper_operator.py
# Should output: "✓ Google Cloud Speech-to-Text initialized"
#               "✓ Google Cloud TTS initialized"
#               "✓ Gemini Vertex AI ready (model: gemini-1.5-flash)"
```

---

## Architecture: How It Works

### Speech Pipeline

```
User speaks
    ↓
[Microphone input captured]
    ↓
[Audio buffer (16kHz, LINEAR16)]
    ↓
Google Cloud Speech-to-Text API
    ↓
Transcribed text (e.g., "Move forward")
    ↓
[input_text_queue] → Operator Worker
```

### Response Generation Pipeline

```
User input: "Move forward"
    ↓
[Prepare conversation history]
    ↓
Gemini 1.5 Flash via Vertex AI
  - System prompt: "You are a helpful robot operator..."
  - Messages: [{"role": "user", "content": "Move forward"}]
  - Temperature: 0.7 (balanced creativity + consistency)
    ↓
Generated response: "I'll move forward now"
    ↓
[output_text_queue] → Audio Manager (TTS)
    ↓
Google Cloud TTS (voice: en-US-Neural2-A)
    ↓
[Audio playback with barge-in support]
```

### Fallback Behavior

**If Google Cloud unavailable:**
```
Google Cloud Speech-to-Text fails
    ↓
Fallback to: Whisper (local model)
    ↓
[Continue normally]

Gemini API timeout
    ↓
Fallback to: FallbackProvider (template responses)
    ↓
Response: "I heard: [user input]. How can I help?"
```

---

## Model Selection

### Gemini Model Variants

**Current Default: gemini-1.5-flash**

| Model | Latency | Cost | Best For |
|-------|---------|------|----------|
| gemini-1.5-flash | 2-5s | Low | Conversational, real-time |
| gemini-1.5-pro | 5-10s | Higher | Complex reasoning, detailed responses |
| gemini-2.0-flash | 1-3s | Low | Fastest, newer model |

**Configure in config.yaml:**
```yaml
operator:
  llm_model: "gemini-1.5-flash"  # Change model here
```

### Alternative LLM Providers (Supported)

**Ollama (Local, Offline)**
```yaml
operator:
  llm_provider: "ollama"
  
# In .env:
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=mistral
```

**Fallback (No Dependencies)**
```yaml
operator:
  llm_provider: "fallback"

# In .env:
LLM_PROVIDER=fallback
```

---

## Cost Estimation

### Google Cloud Pricing (as of 2026)

**Speech-to-Text:**
- ~$0.024 per 15 seconds = ~$0.10/minute
- Monthly (1 hour/day): ~$1800/month

**Text-to-Speech:**
- ~$0.016 per 1000 characters = ~$0.16/call (typical response)
- Monthly (10 responses/hour): ~$300/month

**Vertex AI (Gemini API):**
- Input: ~$0.075 per million tokens
- Output: ~$0.30 per million tokens
- Typical conversation: 500 tokens = ~$0.00015 per response
- Monthly (10 responses/hour): ~$11/month

**Total Estimate:** ~$2000-2500/month for 1 hour/day usage

### Cost Optimization

1. **Use Whisper locally** for ASR (free, but offline)
   - Set `ASR_ENGINE=whisper` in config.yaml
   - Add `faster-whisper` in requirements.txt

2. **Use Ollama locally** for LLM (free, but slower)
   - Set `LLM_PROVIDER=ollama` in config.yaml
   - Run `ollama pull mistral` on Minipupper

3. **Keep TTS as Google Cloud** (quality matters for voice)
   - No good local TTS alternative at this quality level

**Recommended Hybrid Setup:**
```yaml
audio:
  asr:
    engine: "whisper"  # Local (free)
  tts:
    engine: "google"   # Cloud (best quality)

operator:
  llm_provider: "ollama"  # Local (free)
```

---

## Configuration Examples

### Example 1: Full Cloud Setup (Recommended for Best Performance)

```yaml
# config/config.yaml
audio:
  asr:
    engine: "google"
  tts:
    engine: "google"

operator:
  llm_provider: "gemini"
  llm_model: "gemini-1.5-flash"

# .env
ASR_ENGINE=google
LLM_PROVIDER=gemini
LLM_MODEL=gemini-1.5-flash
GOOGLE_APPLICATION_CREDENTIALS=...
GOOGLE_CLOUD_PROJECT_ID=...
```

### Example 2: Hybrid Setup (Cost-Effective)

```yaml
# config/config.yaml
audio:
  asr:
    engine: "whisper"  # Local
  tts:
    engine: "google"   # Cloud

operator:
  llm_provider: "ollama"  # Local

# .env
ASR_ENGINE=whisper
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
# No Google credentials needed for core operation
```

### Example 3: Full Local Setup (Maximum Privacy, Lowest Cost)

```yaml
# config/config.yaml
audio:
  asr:
    engine: "whisper"
  tts:
    engine: "piper"  # Local TTS

operator:
  llm_provider: "ollama"

# .env
ASR_ENGINE=whisper
LLM_PROVIDER=ollama
# No Google credentials needed
```

---

## Troubleshooting

### "Failed to initialize Gemini Vertex AI"

**Cause:** Google Cloud credentials not set or invalid

```bash
# Verify credentials
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json
gcloud auth application-default print-access-token

# Should print a token without errors
```

**Solutions:**
1. Check `GOOGLE_APPLICATION_CREDENTIALS` path is correct
2. Verify service account has Vertex AI User role
3. Ensure APIs are enabled in Google Cloud Console

### "Google Cloud Speech-to-Text failed"

**Cause:** ASR API call failed (rate limit, quota, or API error)

```bash
# Check quota in Google Cloud Console
# https://console.cloud.google.com/apis/dashboard
```

**Solutions:**
1. Verify Speech-to-Text API is enabled
2. Check service account has "Cloud Speech-to-Text Client" role
3. Increase API quotas if needed
4. Fallback to Whisper will activate automatically

### "Gemini timeout"

**Cause:** Vertex AI/Gemini API slow or unavailable

**Solutions:**
1. Check network connectivity to cloud
2. Try smaller model: `gemini-1.5-flash` (default is fast)
3. Use local Ollama as fallback
4. Increase timeout in config.yaml: `response_timeout_seconds: 60`

### "No audio input from microphone"

**Not related to Google Cloud, see [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md#problem-no-audio-input)**

---

## API Limits & Quotas

### Google Cloud Quotas (default)

| API | Limit | Can Increase? |
|-----|-------|---------------|
| Speech-to-Text | 600 requests/min | Yes |
| Text-to-Speech | 4000 requests/min | Yes |
| Vertex AI | Depends on region | Yes |

For robot deployment:
```
Typical: 10-60 requests/hour
Should be well within free tier / standard quotas
```

---

## Monitoring & Debugging

### View API Usage

```bash
# Google Cloud Console
https://console.cloud.google.com/apis/dashboard

# Or via gcloud
gcloud logging read "resource.type=api" --limit=50
```

### Enable Debug Logging

```bash
# In .env
DEBUG=true
LOG_LEVEL=DEBUG

# In config.yaml
logging:
  console_output: true
```

### Test Each Component

```python
# Test Speech-to-Text
from src.audio.audio_manager import AudioManager, AudioConfig
manager = AudioManager(AudioConfig(asr_engine="google"))
text = manager.transcribe_audio("test.wav")
print(f"Transcribed: {text}")

# Test Gemini
from src.core.llm_engine import create_llm_provider, Message
llm = create_llm_provider("gemini")
response = llm.generate_response([Message(role="user", content="Hello")])
print(f"Response: {response}")

# Test TTS
manager.speak("Testing text to speech")
```

---

## Switching Between Models

### From Gemini to Ollama

```bash
# 1. Install Ollama on Minipupper
curl https://ollama.ai/install.sh | sh

# 2. Pull a model
ollama pull mistral  # or llama2, neural-chat, etc.

# 3. Update config/.env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=mistral

# 4. Restart operator
sudo systemctl restart minipupper-operator.service
```

### From Google Cloud Speech to Whisper

```bash
# In config/.env
ASR_ENGINE=whisper
WHISPER_MODEL=base

# Whisper model size trade-offs:
# - tiny: 39MB, very fast, lower accuracy
# - base: 140MB, fast, good accuracy (default)
# - small: 466MB, slower, better accuracy
# - medium: 1.5GB, slow, even better
# - large: 2.9GB, very slow, best accuracy
```

---

## Next Steps

1. **Set up Google Cloud project** (1 hour)
2. **Create service account & download key** (15 min)
3. **Configure .env and config.yaml** (10 min)
4. **Test with `python minipupper_operator.py`** (5 min)
5. **Deploy to Minipupper via systemd** (10 min)

---

**Questions?** See [ARCHITECTURE.md](ARCHITECTURE.md) for system design or [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) for operations.

**Last Updated:** 2026-05-09  
**Status:** Ready for Use
