# Quick Start - Minipupper Operator

Last Updated: 2026-05-10

## 1. Install

```bash
cd /home/minipupper
git clone https://github.com/mangdangroboticsclub/minipupper-app.git
cd minipupper-app

python3.10 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 2. Configure

```bash
cp config/.env.sample config/.env
nano config/.env
```

Set at least:

- GOOGLE_APPLICATION_CREDENTIALS
- GOOGLE_CLOUD_PROJECT_ID

Optional device overrides:

- MIC_DEVICE_INDEX
- SPEAKER_DEVICE_INDEX
- MIC_SAMPLE_RATE (default 16000)

## 3. Run the App

```bash
python minipupper_operator.py
```

## 4. Validate Audio Pipeline

### Pipeline test loop

```bash
python scripts/test_pipeline.py --continuous
```

### Dedicated barge-in loop

```bash
python scripts/test_bargein.py
```

## 5. Calibrate Barge-in AEC/VAD

```bash
python scripts/calibrate_aec.py --duration 5 --write-config
```

Then validate again with the test loops.

Important: if calibration reports quality=low, re-run after verifying device routing and room conditions.

## 6. Common Issues

### False barge-in during TTS (speaker bleed)

- Increase near-end strictness in config/config.yaml:

```yaml
barge_in:
  nearend_mic_to_playback_ratio: 1.25
  nearend_frames_required: 5
  startup_grace_ms: 380
```

### Empty transcripts after interruption

- Use scripts/test_bargein.py to confirm baseline behavior.
- Increase prompt capture duration in test scripts if needed.
- Keep mic gain stable and avoid clipping.

### Frequent VAD fallbacks in test_pipeline

- This indicates VAD did not detect enough valid speech in time.
- Keep speaking until after "Speech started" appears.

## 7. Read Next

- docs/CURRENT_STATE.md
- docs/BARGE_IN_GUIDE.md
- docs/DEPLOYMENT_GUIDE.md
- docs/GOOGLE_CLOUD_SETUP.md
