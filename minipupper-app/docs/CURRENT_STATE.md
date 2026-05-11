# Current State

**Last Updated:** 2026-05-11

## Summary

The app is operational end-to-end with Phase 2 (OpenClaw Agent Integration) in active development.

## Completed

### Phase 1 — Audio Pipeline (Done)
- ✅ ASR: Google Cloud Speech-to-Text primary, Whisper fallback path
- ✅ LLM: Gemini Vertex AI (gemini-2.5-flash)
- ✅ TTS: Google Cloud TTS with interruptible playback
- ✅ Barge-in: streaming VAD with in-app reference AEC and near-end gating
- ✅ Conversation management with context window
- ✅ Queue-based worker architecture

### Phase 2 — OpenClaw Agent Integration (In Progress)
- ✅ **File-based task protocol** — shared `tasks.json` replaces session messaging
- ✅ **Gemini task offloading** — `[TASK]` markers in system prompt
- ✅ **TaskWatcher** — polls file every 2s, announces completed tasks via LLM+TTS
- ✅ **TaskArchiver** — date-partitioned archive of completed tasks
- ✅ **Gateway cron processor** — polls every 5s, executes web_search, robot.* tasks
- ✅ **Announced flag** — prevents re-announcement across restarts
- ✅ **Auto-cleanup** — announced+completed tasks moved to archive
- ✅ **OpenClaw node connection** — stable via Tailscale TLS
- ✅ **Shared session** for app↔Gateway communication

## Known Issues

- Cor cron isolated agent startup adds ~10s latency per task
- File-based polling has inherent ~5-7s delay (cron interval + model startup)
- Some speaker bleed causes false interruption events (Phase 1 issue)
- gemini-2.5-flash model name in config not 1.5-flash (upgrade)

## Quick Test

```bash
python minipupper_operator.py
# Say: "what's the weather in Beijing"
# Expect: ~15-20s response time via Gateway agent
```

## Key Files

| File | Purpose |
|------|---------|
| `minipupper_operator.py` | Main application entry point |
| `config/system_prompt_phase2.txt` | Gemini prompt with Phase 2 offloading |
| `src/core/task_watcher.py` | Watches `tasks.json`, announces completions |
| `src/core/task_archiver.py` | Archives completed tasks to history |
| `src/core/llm_engine.py` | LLM abstraction (Gemini, Ollama, fallback) |
| `src/audio/audio_manager.py` | ASR/TTS with barge-in |
| `tasks.json` | Shared task file (app ↔ Gateway agent) |
| `PHASE2.md` | Full Phase 2 protocol documentation |

## Scope of Current Docs

- README.md: project overview and current architecture
- QUICKSTART.md: setup and run commands
- PHASE2.md: Phase 2 protocol and architecture
- docs/BARGE_IN_GUIDE.md: barge-in internals and tuning
- docs/DEPLOYMENT_GUIDE.md: operational guidance
- docs/TASK_ARCHIVING.md: task archival system
- docs/CURRENT_STATE.md: this file
