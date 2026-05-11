# Development Roadmap - Minipupper Operator

**Status:** Phase 2 Active — OpenClaw Agent Integration (Updated 2026-05-11)  
**Vision:** Autonomous voice-first AI assistant for Minipupper robots

---

## Phase 1: Foundation & Audio (✅ Complete — 2026-05-09)
**Duration:** 1 week

### ✅ Delivered
- Audio pipeline (Google Cloud STT, TTS, barge-in)
- Gemini LLM integration (Vertex AI, Ollama fallback)
- Queue-based worker architecture
- Barge-in detection with AEC
- Configuration system

---

## Phase 2: OpenClaw Agent Integration (Active — May 2026)
**Duration:** ~1 week | **Started:** 2026-05-11

### ✅ Delivered (May 11)
- **File-based task protocol** — shared `tasks.json` replaces session messaging
- **Gemini task offloading** — `[TASK]` markers in system prompt
- **TaskWatcher** — polls file, announces completions, tracks with `announced` flag
- **TaskArchiver** — date-partitioned archive, non-destructive
- **Gateway cron processor** — 5s poll for pending tasks
- **Auto-cleanup** — announced+completed tasks moved to archive
- **All components tested** — web_search, robot.move_right, robot.disable

### In Progress
- **Latency reduction** — current 15-20s, target <5s
- **Persistent file watcher** — replace cron polling with event-driven approach

### Success Criteria
- [x] Task offloading works (Gemini → Gateway)
- [x] Task execution works (web_search, robot.*)
- [x] Task announcements work (TaskWatcher → TTS)
- [x] Archive system works (history + cleanup)
- [ ] Response time < 10 seconds (current ~15-20s)
- [ ] Event-driven triggers (no polling)

---

## Phase 3: Robot Control (June 2026)
**Duration:** 2-3 weeks | **Target:** 2026-06-15

### Pending
- ⏳ Movement API refinement
- ⏳ Sensor integration (IMU, distance, battery)
- ⏳ Safety limits and validation
- ⏳ Hardware testing on Minipupper

### Success Criteria
- [ ] All basic movements work via voice
- [ ] Safety limits enforced
- [ ] Sensor feedback integrated

---

## Phase 4: Production Hardening (July-August 2026)
**Duration:** 4 weeks | **Target:** 2026-08-15

### Pending
- ⏳ Performance optimization
- ⏳ 72-hour stability test
- ⏳ Documentation complete
- ⏳ v0.1.0-beta release

---

## Resource Requirements

### Hardware
- 1x Minipupper robot (dev/test)
- 1x Cloud server (OpenClaw Gateway)
- Tailscale network for secure connectivity

### Infrastructure
- Git repository (private)
- OpenClaw Gateway (self-hosted)
- Google Cloud (STT, TTS, Vertex AI)

---

## Key Technical Decisions

| Decision | Rationale |
|----------|-----------|
| File-based over session-based protocol | Eliminates session pollution, stale message replay issues |
| `announced` flag over in-memory tracking | Persists across restarts, no re-announcement |
| Isolated cron for task execution | Can use agent tools (web_search, web_fetch) |
| Non-destructive archive | Prevents race condition with concurrent file writes |
| Gemini 2.5-flash | Faster responses than 1.5-flash |
| Node exec for file access | Allows gateway to read/write Pi filesystem securely |

---

**Roadmap Version:** 1.1  
**Last Updated:** 2026-05-11
