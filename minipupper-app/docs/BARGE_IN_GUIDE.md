# Barge-in Implementation Guide

**Last Updated:** 2026-05-09  
**Status:** Early Implementation  
**Relevant Code:** `src/audio/barge_in_detector.py`, `src/audio/audio_manager.py`

---

## 1. What is Barge-in?

**Barge-in** is the ability for a user to interrupt robot speech by speaking over it. When the robot is talking, if the user starts speaking, the robot immediately stops talking and begins listening to the user's new input.

### Why It Matters
- **Natural Interaction:** Humans expect to interrupt each other in conversations
- **Responsiveness:** User feels heard immediately, not forced to wait
- **Safety:** User can issue emergency commands without waiting for speech to finish

---

## 2. How It Works

### 2.1 Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Audio Manager                            │
│                                                             │
│  ┌────────────────────────────────────────────────────┐   │
│  │              TTS (Speaking)                        │   │
│  │         Plays response audio in chunks             │   │
│  │            ↓                                        │   │
│  │       Check interrupt_event                        │   │
│  │            ↓                                        │   │
│  │       If set → STOP PLAYBACK                       │   │
│  └────────────────────────────────────────────────────┘   │
│                       │                                    │
│                       │ Parallel monitoring                │
│                       │                                    │
│  ┌────────────────────▼────────────────────────────────┐   │
│  │         Barge-in Detector (separate thread)         │   │
│  │                                                     │   │
│  │  Listen to microphone continuously                 │   │
│  │        ↓                                             │   │
│  │  Detect speech energy above threshold              │   │
│  │        ↓                                             │   │
│  │  Signal → Audio Manager via callback               │   │
│  │        ↓                                             │   │
│  │  on_barge_in() → Sets interrupt_event              │   │
│  │                                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Key Components

**BargeInDetector** (`src/audio/barge_in_detector.py`)
- Runs in its own thread
- Continuously monitors microphone for speech
- Uses energy-based detection (simple, fast)
- Optional VAD (Voice Activity Detection) for future enhancement
- Triggers callback when speech detected

**AudioManager** (`src/audio/audio_manager.py`)
- Manages ASR and TTS
- Launches barge-in detector before speaking
- Plays audio in chunks to allow interrupt checks
- Stops playback when interrupt signal received

---

## 3. Configuration Parameters

### Energy Threshold
```yaml
barge_in:
  min_energy_threshold: 500  # Default: 500
```

**What it means:**
- Speech energy (RMS) must exceed this value to trigger interrupt
- **Too low:** False positives (background noise triggers interrupt)
- **Too high:** Misses user speech

**How to tune:**
1. Run detector with noise floor in environment
2. Record baseline noise energy
3. Set threshold to ~3-5x noise energy
4. Test with actual speech

### Detection Timeout
```yaml
barge_in:
  detection_timeout_ms: 500  # Default: 500 ms
```

**What it means:**
- Max time to wait for speech energy to exceed threshold
- **Too low:** May miss slower speech onset
- **Too high:** Delayed interrupt response

### Silence Duration
```yaml
barge_in:
  silence_duration_ms: 300  # Default: 300 ms
```

**What it means:**
- How long silence must last before resetting speech detection
- Prevents false resets from brief pauses in speech

---

## 4. Implementation Details

### 4.1 Energy-Based Detection

The detector monitors microphone input in real-time and calculates **RMS energy**:

```python
# Calculate energy from audio chunk
audio_chunk = [sample1, sample2, ..., sampleN]
energy = sqrt(mean(audio_chunk^2))  # RMS energy

# Compare to threshold
if energy > min_energy_threshold:
    # User is speaking!
    trigger_barge_in()
```

### 4.2 Detection Flow

```
Start TTS playback
    │
    └─► Start barge_in_detector.start_listening()
            │
            ├─► Spawn audio monitoring thread
            │
            └─► Set on_barge_in callback
                    │
                    └─► play_audio_chunk()
                            │
                            ├─► Check interrupt_event
                            │
                            └─► If set:
                                    STOP PLAYBACK
                                    detector.stop_listening()
                                    Return False (interrupted)

User speaks during playback
    │
    └─► Microphone input energy spikes
            │
            └─► Detector detects threshold crossing
                    │
                    └─► Call on_barge_in() callback
                            │
                            └─► Sets interrupt_event
                                    │
                                    └─► Next chunk loop sees flag
                                            │
                                            └─► STOP and return
```

---

## 5. Testing the Barge-in Feature

### 5.1 Manual Test - Detector Only

```bash
# Run detector standalone
python -m src.audio.barge_in_detector

# Output:
# Listening for barge-in... Press Ctrl+C to stop
# Try speaking while this is running

# Terminal output when you speak:
# Speech detected (energy: 650.5)
# Silence detected - reset
```

### 5.2 Manual Test - Audio Manager with TTS

```python
from src.audio.audio_manager import AudioManager, AudioConfig

manager = AudioManager(AudioConfig())

def on_interrupted():
    print(">>> USER INTERRUPTED SPEECH <<<")

manager.on_interrupted = on_interrupted

# Test speaking with barge-in
interrupted = manager.speak("Say something while I'm talking")

if interrupted:
    print("Speech was interrupted!")
else:
    print("Speech completed normally")
```

### 5.3 Integration Test - Full Conversation

```python
# Test script
from src.core.task_queue import input_text_queue, output_text_queue
from minipupper_operator import MinipupperOperator

operator = MinipupperOperator()
operator.start()

# Simulate user saying "Move forward"
input_text_queue.put("Move forward")

# Robot will speak response and listen for interruption
# You can speak to interrupt mid-response
```

---

## 6. Troubleshooting

### Problem: False Positives (noise triggers interrupt)

**Symptoms:**
- Robot cuts off mid-sentence for no reason
- Happens in noisy environments (fan, traffic, etc.)

**Solutions:**
1. **Increase threshold** in `config.yaml`:
   ```yaml
   barge_in:
     min_energy_threshold: 800  # Was 500
   ```

2. **Increase silence duration** to debounce:
   ```yaml
   barge_in:
     silence_duration_ms: 500  # Was 300
   ```

3. **Disable barge-in** temporarily:
   ```yaml
   barge_in:
     enabled: false
   ```

### Problem: Missing interrupts (user speech not detected)

**Symptoms:**
- User can't interrupt robot speech
- Has to wait for speech to finish

**Solutions:**
1. **Lower threshold** in `config.yaml`:
   ```yaml
   barge_in:
     min_energy_threshold: 300  # Was 500
   ```

2. **Check microphone levels:**
   ```bash
   # Test microphone input
   python -c "
   import sounddevice as sd
   import numpy as np
   
   stream = sd.InputStream()
   with stream:
       data, _ = stream.read(16000)  # 1 second of audio
       print(f'Energy level: {np.sqrt(np.mean(data**2)):.1f}')
   "
   ```

3. **Check microphone selection:**
   ```yaml
   # In config/.env
   AUDIO_DEVICE_INDEX=-1  # -1 = default
   
   # List devices:
   python -c "import sounddevice; print(sounddevice.query_devices())"
   ```

### Problem: Choppy/Delayed Response

**Symptoms:**
- Robot speech sounds choppy
- Large delay before interruption response

**Solutions:**
1. **Reduce chunk size** in `audio_manager.py`:
   ```python
   chunk_size = 2048  # Was 4096 - smaller chunks = faster checks
   ```

2. **Reduce timeout** in `config.yaml`:
   ```yaml
   barge_in:
     detection_timeout_ms: 200  # Was 500 - faster detection
   ```

---

## 7. Future Enhancements

### 7.1 Voice Activity Detection (VAD)
Replace simple energy detection with ML-based VAD:
```python
# Pseudo-code: Add VAD model
from pyannote_audio import Pipeline

vad_pipeline = Pipeline.from_pretrained("pyannote/voice-activity-detection")

# Use in detector:
vad_confidence = vad_pipeline(audio_chunk)
if vad_confidence > voice_activity_threshold:  # 0.5
    trigger_barge_in()
```

**Benefits:**
- More accurate (fewer false positives)
- Better for noisy environments
- Distinguishes speech from other sounds

**Trade-offs:**
- Slower (ML inference overhead)
- More CPU/memory required

### 7.2 Multi-User Support
Detect who is speaking (speaker diarization):
```yaml
operator:
  multi_user: true  # Allow multiple speakers
  
  users:
    - name: "owner"
      priority: 100  # Owner can always interrupt
    - name: "guest"
      priority: 50   # Guest lower priority
```

### 7.3 Context-Aware Interruption
Different barge-in thresholds for different conversation contexts:
```yaml
barge_in:
  contexts:
    alarm: 100      # Easy to interrupt alarm
    critical: 1000  # Hard to interrupt critical alert
    normal: 500     # Default conversation
```

### 7.4 Barge-in Confirmation
Ask user to confirm if interrupt was intentional:
```
Robot: "I was about to tell you the weather. Should I continue or start over?"
```

---

## 8. Performance Characteristics

### Latency Breakdown
```
User speaks
    ↓
[0-100ms] Audio captured in buffer
    ↓
[100-200ms] Energy calculated on chunk
    ↓
[200-300ms] Threshold check
    ↓
[300-500ms] Callback triggered, interrupt_event set
    ↓
[500-550ms] TTS playback stops (next chunk loop)
    ↓
Total: ~500ms max latency from speech to stop
```

### CPU Usage
- **Detector thread:** ~5-10% CPU (continuous monitoring)
- **TTS playback:** ~2-5% CPU (audio output)
- **Total during speech:** ~10-15% CPU

### Memory Usage
- **Detector:** ~20 MB (audio buffers)
- **Audio Manager:** ~50 MB (TTS cache, audio streams)
- **Total:** ~70 MB overhead (negligible on 8GB Raspberry Pi)

---

## 9. References & Further Reading

### Related Code Files
- [BargeInDetector Class](../src/audio/barge_in_detector.py)
- [AudioManager Integration](../src/audio/audio_manager.py)
- [Configuration](../config/config.yaml)

### External Resources
- **Whisper (ASR):** https://github.com/openai/whisper
- **faster-whisper:** https://github.com/guillaumekln/faster-whisper
- **pyannote-audio (VAD):** https://github.com/pyannote/pyannote-audio
- **Barge-in in Telephony:** https://www.voiceofcustomer.com/barge-in-in-ivr/

---

**Last Updated:** 2026-05-09  
**Next Review:** 2026-05-20 (after initial testing)
