# Phase 3 Overhaul — Fixing the Task Pipeline

**Date:** 2026-05-12

---

## Problems Identified

1. **Cron can't handle explore/implement** — isolated agentTurn has no context
2. **Gemini doesn't know task results** — no feedback into conversation history
3. **No feedback loop** — "let's try it" → Gemini re-creates the same implement task
4. **No knowledge base reference** — Gemini has no instructions to check existing knowledge

## Fix: Dual-Path Task Routing

### Path A: Known Actions (cron-based)
`web_search`, `web_fetch`, `robot.*`, `query` → written to tasks.json → cron.run → isolated agent processes

### Path B: Explore/Implement (main agent)
`explore`, `implement` → written to tasks.json (for tracking) + structured session message sent to main agent → main agent processes during heartbeat

### Result Injection
When TaskWatcher announces a completed task, it calls `on_result` callback → appends to Gemini's `conversation_history` → next turn Gemini knows what happened

## Files Changed

| File | Change |
|------|--------|
| `minipupper_operator.py` | Added `_on_task_result()` callback, session message send for explore/implement |
| `src/core/task_watcher.py` | Added `on_result` callback parameter, calls it after successful TTS |
| `config/system_prompt_phase2.txt` | Added knowledge base reference and result awareness instructions |
| `knowledge/INDEX.json` | Populated with camera, IMU, battery, motors topics |
| `knowledge/camera.md` | Detailed camera capabilities |
| `knowledge/imu.md` | IMU sensor info |
| `knowledge/battery.md` | Battery/power info |
| `knowledge/motors.md` | Servo/motor control info |

## Gateway Side Changes

| File | Change |
|------|--------|
| `task_handler.py` | Added 4 new handlers (explore, implement, take_photo_and_show, show_image) |
| `HEARTBEAT.md` | Updated with explore/implement session message processing instructions |
| Cron job message | Updated to SKIP explore/implement (main agent handles them) |
