# Current State

Last Updated: 2026-05-10

## Summary

The app is operational end-to-end:

- ASR: Google Cloud Speech-to-Text primary, Whisper fallback path
- LLM: Gemini Vertex primary
- TTS: Google Cloud TTS with interruptible playback
- Barge-in: streaming VAD with in-app reference AEC and near-end gating

## What Works Reliably

- Normal speech-to-response loop
- Most user interruptions while TTS is active
- Recovery from missed VAD capture in test_pipeline via fixed-duration fallback

## Known Issues (Observed in Real Logs)

- Some speaker bleed still causes false interruption events.
- Some interrupted utterances are too short/noisy and transcribe as empty text.
- Calibration can report low quality when playback-to-mic coupling is weak, resulting in low-confidence suggested values.

## Why This Happens

- In-app AEC is heuristic and depends on accurate playback reference alignment.
- Acoustic path changes (robot posture, room reflections, speaker volume) can invalidate tuned values.
- Interruption often produces short fragments that are below reliable ASR threshold.

## Recommended Test Order

1. python scripts/calibrate_aec.py --duration 5 --write-config
2. Verify calibration_quality is medium/high.
3. python scripts/test_bargein.py
4. python scripts/test_pipeline.py --continuous

If quality is low, do not trust the written values without manual tightening.

## Manual Tightening Baseline

```yaml
barge_in:
  nearend_mic_to_playback_ratio: 1.25
  nearend_frames_required: 5
  startup_grace_ms: 380
```

## Scope of Current Docs

- README.md: project overview and current architecture
- QUICKSTART.md: setup and run commands
- docs/BARGE_IN_GUIDE.md: barge-in internals and tuning
- docs/DEPLOYMENT_GUIDE.md: operational guidance
