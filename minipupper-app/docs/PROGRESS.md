# Minipupper Operator - Development Progress Log

**Project Start Date:** 2026-05-09  
**Status:** Audio Pipeline Complete (Phase 1 Done)  
**Team:** Minipupper Team

---

## 2026-05-09 - Project Initialization & Google Cloud Integration

### Completed
- ✅ Project structure established
  - `src/core/` - Core application logic
  - `src/audio/` - Audio I/O and barge-in detection
  - `src/robot/` - Robot-specific movement controls
  - `config/` - Configuration files
  
- ✅ Core modules scaffolded
  - `task_queue.py` - Inter-component communication (queues)
  - `barge_in_detector.py` - Speech interruption detection
  - `audio_manager.py` - ASR/TTS integration with barge-in
  - `minipupper_operator.py` - Main operator application
  - `llm_engine.py` - LLM provider abstraction (NEW)
  
- ✅ **Google Cloud Integration**
  - `audio_manager.py` - **Google Cloud Speech-to-Text API** (primary ASR)
  - Whisper fallback support (local backup)
  - Google Cloud Text-to-Speech (TTS)
  
- ✅ **Gemini Integration**
  - `llm_engine.py` - **Gemini 1.5 Flash via Vertex AI** (primary LLM)
  - Ollama support (local LLM fallback)
  - Fallback provider (simple template responses)
  
- ✅ Configuration system
  - `config.yaml` - Updated for Google Cloud + Gemini
  - `.env.sample` - Google Cloud credentials setup
  - YAML-based settings (audio, barge-in, operator, network)
  
- ✅ Documentation foundation
  - Development log (this file)
  - Architecture documentation
  - Barge-in implementation guide
  - Testing plan
  - Deployment guide
  - **NEW: Google Cloud & Gemini setup guide**

### In Progress
- 🔄 ASR streaming optimization (Google Cloud Speech)
- 🔄 LLM context window optimization
- 🔄 Robot movement control APIs

### Next Steps (by priority)
1. **Operator Logic Testing** - Validate Gemini responses
   - Test conversation flow with real Gemini API
   - Validate context window management
   - Stress test with multiple turns
   
2. **ASR Streaming** - Implement streaming for lower latency
   - Use Google Cloud streaming API
   - Reduce transcription latency
   
3. **Robot Control** - Movement command mapping
   - Implement motor control APIs (if available)
   - Test motion on Minipupper hardware
   - Safety validation
   
4. **Integration Testing** - Full system validation
   - End-to-end conversation tests
   - Barge-in stress testing
   - Network reliability (Tailscale)

---

## Models in Use

### Speech-to-Text (ASR)
- **Primary:** Google Cloud Speech-to-Text API
  - 95%+ accuracy
  - Multiple language support
  - Real-time streaming capable
  
- **Fallback:** Whisper (faster-whisper)
  - Local, offline
  - Lower accuracy
  - Free

### Large Language Model (LLM)
- **Primary:** Gemini 1.5 Flash via Vertex AI
  - Fast responses (2-5 seconds)
  - Multimodal capable
  - State-of-the-art reasoning
  
- **Fallback 1:** Ollama (local)
  - Offline operation
  - Lower quality responses
  - Free
  
- **Fallback 2:** Template responses
  - Always works
  - Limited functionality

### Text-to-Speech (TTS)
- **Primary:** Google Cloud Text-to-Speech
  - Natural sounding voices
  - 39 languages
  - Barge-in compatible

---

## Notes for Developers

### Key Design Decisions
1. **Queue-based Architecture** - Mimics reference `ai-app` for consistency
2. **Multi-Provider LLM** - Easy to swap between Gemini, Ollama, fallback
3. **Operator-only Role** - No OpenClaw dependency; all capabilities local
4. **Barge-in First** - Interruption support built-in from start
5. **Cloud First, Local Fallback** - Google Cloud for best quality, Whisper/Ollama for offline

### Important Files
- **Config:** `config/config.yaml` - Adjust LLM model, ASR engine here
- **Audio:** `src/audio/` - All speech I/O logic
- **LLM:** `src/core/llm_engine.py` - Add new LLM providers here
- **Main App:** `minipupper_operator.py` - Application entry point
- **Setup:** `docs/GOOGLE_CLOUD_SETUP.md` - Google Cloud credential setup

### Environment Setup
```bash
cd minipupper-app
python -m pip install -r requirements.txt
cp config/.env.sample config/.env
# Edit config/.env with Google Cloud credentials
python minipupper_operator.py
```

### Testing Modules

**Test Barge-in Locally**
```bash
python -m src.audio.barge_in_detector
```

**Test Gemini LLM**
```bash
python -c "
from src.core.llm_engine import create_llm_provider, Message
llm = create_llm_provider('gemini')
response = llm.generate_response([Message(role='user', content='Hello')])
print(response)
"
```

**Test Google Cloud Speech**
```bash
python -c "
from src.audio.audio_manager import AudioManager, AudioConfig
manager = AudioManager(AudioConfig(asr_engine='google'))
text = manager.transcribe_audio('test.wav')
print(f'Transcribed: {text}')
"
```

---

## Dates for Review & Milestones

| Date | Milestone | Owner | Status |
|------|-----------|-------|--------|
| 2026-05-09 | Project Setup + Google Cloud Integration | - | ✅ Done |
| 2026-05-15 | LLM Response Testing | - | ⏳ Planned |
| 2026-05-20 | ASR Streaming Optimization | - | ⏳ Planned |
| 2026-05-25 | Robot Control APIs | - | ⏳ Planned |
| 2026-06-01 | Integration Test | - | ⏳ Planned |
| 2026-06-10 | Beta Release | - | ⏳ Planned |

---

## Questions & Decisions Log

**Q: Which LLM provider to use?**  
*Decision: Gemini 1.5 Flash (fast, capable, reasonable cost)* ✅

**Q: How to support offline operation?**  
*Decision: Fallback to Ollama + Whisper with local models* ✅

**Q: How to integrate with existing Minipupper APIs?**  
*Decision pending* - Need to review existing robot control code

**Q: Cost optimization strategy?**  
*Decision: Hybrid mode recommended (Whisper ASR + Ollama LLM, cloud TTS)* ✅

---

**Last Updated:** 2026-05-09  
**Next Review:** 2026-05-15

