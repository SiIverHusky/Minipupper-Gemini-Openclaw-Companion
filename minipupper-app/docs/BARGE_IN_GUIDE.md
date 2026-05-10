# Barge-in Guide

Last Updated: 2026-05-10
Status: Active tuning

## What Barge-in Means Here

Barge-in lets the user interrupt TTS while the robot is speaking.

Current behavior:

- Works in most interactions.
- Can still false-trigger from speaker bleed in some acoustic setups.
- Interrupted follow-up utterances may be short and transcribe poorly.

## Current Detection Pipeline

Code path:

- src/audio/audio_manager.py
- src/audio/barge_in_detector.py

Flow:

1. TTS starts playback.
2. Playback PCM frames are fed to the detector as far-end reference.
3. Detector runs lightweight reference AEC on mic frame.
4. WebRTC VAD runs on cleaned frame.
5. Echo similarity suppression checks raw mic vs playback.
6. Near-end gate enforces user-dominant speech conditions.
7. Startup grace suppresses early false triggers while AEC aligns.
8. Consecutive valid frames trigger interruption.

## Tunable Settings

From config/config.yaml, section barge_in:

- vad_aggressiveness
- detection_timeout_ms
- silence_duration_ms
- frame_duration_ms
- aec_enabled
- aec_max_delay_ms
- aec_max_gain
- aec_double_talk_ratio
- echo_suppression_threshold
- echo_energy_ratio
- nearend_min_cleaned_rms
- nearend_mic_to_playback_ratio
- nearend_frames_required
- startup_grace_ms

## Calibration

Use:

```bash
python scripts/calibrate_aec.py --duration 5 --write-config
```

The script reports:

- estimated_delay_ms
- estimated_gain
- estimated_erle_db
- calibration_quality

Interpretation:

- high: good confidence, use output as-is.
- medium: usable baseline, verify with conversation tests.
- low: weak coupling detected; values may under-protect against bleed.

When quality is low:

- Verify correct input/output devices.
- Increase speaker volume to normal runtime level.
- Calibrate in a quiet room with no speech.
- Re-run 2-3 times and compare.

## Practical Tuning Patterns

### If speaker bleed still interrupts TTS

Increase strictness:

```yaml
barge_in:
  nearend_mic_to_playback_ratio: 1.25
  nearend_frames_required: 5
  startup_grace_ms: 380
```

### If real user interruptions are missed

Reduce strictness slightly:

```yaml
barge_in:
  nearend_mic_to_playback_ratio: 1.05
  nearend_frames_required: 3
  startup_grace_ms: 250
```

### If overlap speech sounds clipped or ignored

```yaml
barge_in:
  aec_double_talk_ratio: 1.5
  aec_max_gain: 1.0
```

## Test Scripts and Expectations

scripts/test_pipeline.py --continuous:

- VAD-first capture.
- Falls back to fixed recording if VAD capture is empty.
- Good for stress-testing edge cases.

scripts/test_bargein.py:

- Fixed prompt recording before LLM/TTS.
- Better baseline for checking barge-in behavior itself.

## Known Limitations

- This is in-app heuristic AEC, not full WebRTC AEC module.
- Acoustic geometry (speaker/mic placement, enclosure reflections) heavily affects false-trigger rate.
- Short interrupted utterances may still produce empty transcripts.

## Recommended Operating Procedure

1. Run calibration.
2. Reject low-quality calibration runs.
3. Validate with test_bargein first.
4. Stress-test with test_pipeline continuous mode.
5. Apply incremental tuning only to 1-2 parameters at a time.
