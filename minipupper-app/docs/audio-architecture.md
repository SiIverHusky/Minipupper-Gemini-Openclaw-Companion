# Audio Architecture — Minipupper Phase 2

## Overview

The Minipupper uses a two-sound-card ALSA topology for its audio hardware.
Acoustic Echo Cancellation (AEC) is handled by PulseAudio's built-in WebRTC
module to prevent the robot's own speech from bleeding into the microphone
and triggering false voice activity detection.

## Hardware Topology

```
┌──────────────────────────────────────────────────────────┐
│                    Raspberry Pi 4                        │
│                                                          │
│  Card 0: bcm2835 Headphones (3.5mm jack)                │
│          hw:0,0 — 8 output channels, 0 input channels    │
│          Driver: bcm2835_headpho                         │
│          └─ Speaker (physical)                           │
│                                                          │
│  Card 1: snd_rpi_simple_card (I2S codec)                │
│          hw:1,0 — 2 output, 2 input channels             │
│          Driver: snd_soc_simple_card                     │
│          ├─ Microphone (physical, works)                 │
│          └─ Codec output (broken/timeouts)               │
│                                                          │
│  ┌──────────────────────────────────────────────────┐    │
│  │            PulseAudio Server                     │    │
│  │  (pulseaudio-aec.service — systemd user unit)    │    │
│  │                                                   │    │
│  │  Sources:                                         │    │
│  │    alsa_input...simple-card.0.analog-stereo       │    │
│  │      └─ Raw I2S mic                               │    │
│  │    aec_source_hp (module-echo-cancel)             │    │
│  │      └─ Echo-cancelled mic ← APP CAPTURES FROM    │    │
│  │                                                   │    │
│  │  Sinks:                                           │    │
│  │    alsa_output...bcm2835_audio.analog-stereo      │    │
│  │      └─ Headphone jack speaker                    │    │
│  │    aec_sink_hp (module-echo-cancel)               │    │
│  │      └─ Echo reference + speaker ← APP PLAYS TO   │    │
│  └──────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────┘
```

## Audio Signal Flow

```
┌──────────────┐    ┌────────────────┐    ┌──────────────────┐
│  Operator    │    │  sounddevice   │    │  ALSA default    │
│  App         │───▶│  (PortAudio)   │───▶│  ("default" PCM) │
│  (capture)   │    │                │    │                  │
│  (playback)  │    │  device=-1     │    │  libasound2-     │
└──────────────┘    └────────────────┘    │  plugins (pulse) │
       │                                  └────────┬─────────┘
       │                                           │
       ▼                                           ▼
┌──────────────────┐                    ┌──────────────────┐
│  aec_source_hp   │                    │   aec_sink_hp    │
│  (echo removed)  │                    │                  │
└───────┬──────────┘                    └────────┬─────────┘
        │                                        │
        │  ┌─────────────────────────────┐       │
        │  │  module-echo-cancel         │       │
        │  │  aec_method=webrtc          │       │
        │  │  source_master=I2S mic      │◀──────┘
        │  │  sink_master=headphone jack │  (echo reference)
        │  │  noise_suppression=1        │
        │  │  analog_gain_control=0      │
        │  └─────────────────────────────┘
        │
        ▼
┌──────────────────┐
│  ALSA I2S mic    │
│  (card 1, hw:1,0)│
└──────────────────┘

Sound emerges from the speaker when:
  aec_sink_hp → module-echo-cancel → alsa_output...bcm2835_audio.analog-stereo → card 0 (headphone jack)
```

## Key Files

### On the Pi (Raspberry Pi / `ubuntu` user)

| File | Purpose |
|------|---------|
| `~/.config/pulse/default.pa` | PulseAudio startup config — loads WebRTC AEC with correct I2S-mic/headphone-jack pairing |
| `~/.config/systemd/user/pulseaudio-aec.service` | Systemd user service — auto-starts PulseAudio with AEC on boot |
| `~/.asoundrc` | ALSA custom devices (`aec_mic`, `aec_speaker`) for explicit routing through PulseAudio AEC |
| `~/minipupper-app/config/config.yaml` | App config — uses `input_device: -1`, `output_device: -1` (default = PulseAudio AEC chain) |
| `~/minipupper-app/scripts/start_with_aec.sh` | Launcher script — ensures PulseAudio + AEC is running before starting the operator |

## PulseAudio Configuration

### `~/.config/pulse/default.pa`

```pulseaudio
#!/usr/bin/pulseaudio -nF
.include /etc/pulse/default.pa

### ── WebRTC AEC ──
### Source: I2S mic (simple-card) | Sink: headphone jack (bcm2835)
load-module module-echo-cancel \
    source_master=alsa_input.platform-asoc-simple-card.0.analog-stereo \
    sink_master=alsa_output.platform-bcm2835_audio.analog-stereo \
    aec_method=webrtc \
    source_name=aec_source_hp \
    sink_name=aec_sink_hp \
    aec_args="analog_gain_control=0 digital_gain_control=1 noise_suppression=1"

set-default-sink aec_sink_hp
set-default-source aec_source_hp
```

### Systemd Service: `~/.config/systemd/user/pulseaudio-aec.service`

```ini
[Unit]
Description=PulseAudio with WebRTC Acoustic Echo Cancellation
After=sound.target

[Service]
ExecStartPre=/bin/bash -c '/usr/bin/pulseaudio --kill 2>/dev/null; exit 0'
ExecStartPre=sleep 0.3
ExecStart=/usr/bin/pulseaudio --daemonize=no --exit-idle-time=-1 --realtime
ExecStartPost=/bin/bash -c 'sleep 1; \
  pactl load-module module-echo-cancel \
    source_master=alsa_input.platform-asoc-simple-card.0.analog-stereo \
    sink_master=alsa_output.platform-bcm2835_audio.analog-stereo \
    aec_method=webrtc \
    source_name=aec_source_hp \
    sink_name=aec_sink_hp \
    aec_args=analog_gain_control=0,digital_gain_control=1,noise_suppression=1 2>/dev/null; \
  pactl set-default-source aec_source_hp 2>/dev/null; \
  pactl set-default-sink aec_sink_hp 2>/dev/null'
Restart=on-failure
RestartSec=2

[Install]
WantedBy=default.target
```

## App Config: Audio Section (`config.yaml`)

```yaml
audio:
  channels: 1
  input_device: -1          # ALSA default → PulseAudio → aec_source_hp
  output_device: -1         # ALSA default → PulseAudio → aec_sink_hp
  sample_rate: 16000
  asr:
    engine: google
    language: en-US
    streaming: true
  tts:
    engine: google
    voice: en-US-Neural2-A
```

The `-1` device ID tells sounddevice to use the ALSA `default` PCM, which
routes through the ALSA PulseAudio plugin (`libasound2-plugins`), which
forwards to PulseAudio's default source/sink — set to the AEC devices.

## Acoustic Echo Cancellation Parameters

The WebRTC AEC module uses:

| Parameter | Value | Effect |
|-----------|-------|--------|
| `aec_method` | `webrtc` | WebRTC AEC algorithm (best quality on ARM64) |
| `noise_suppression` | `1` | Mild noise suppression (0=off, 1=mild, 2=aggressive) |
| `analog_gain_control` | `0` | Disabled — the I2S codec handles gain |
| `digital_gain_control` | `1` | Enabled — prevents clipping |

The AEC module creates two virtual devices:
- **`aec_source_hp`** — echo-cancelled microphone (the app captures from here)
- **`aec_sink_hp`** — echo reference sink (the app plays to here; audio is forwarded to the physical speaker AND used as the echo reference)

## Why Not PulseAudio's Default AEC Sink Pair

The first attempt used both source and sink on the I2S simple-card
(`sink_master=alsa_output.platform-asoc-simple-card.0.analog-stereo`).
This failed because the simple-card's **playback path is non-functional**
(ALSA `snd_soc_simple_card` dummy codec with a broken DAI). The output
device opens but hangs on actual audio I/O. The only working playback
path is the bcm2835 headphone jack (card 0).

However, the `module-echo-cancel` **does** work with source and sink on
different physical cards — `source_master`=I2S mic, `sink_master`=headphone
jack. This is the configuration used in production.

## Troubleshooting

### No sound from speaker

```bash
# Verify PulseAudio is running with AEC
pactl info
pactl list sources short | grep aec_source_hp
pactl get-default-source  # should be aec_source_hp
pactl get-default-sink    # should be aec_sink_hp

# Direct test: play a WAV through the AEC sink
paplay --device=aec_sink_hp /tmp/test.wav

# Direct ALSA test (bypasses PulseAudio)
speaker-test -D hw:0,0 -c 2 -l 1 -t sine -f 440
```

### AEC not loaded

```bash
# Check service status
systemctl --user status pulseaudio-aec.service

# Load manually
pactl load-module module-echo-cancel \
    source_master=alsa_input.platform-asoc-simple-card.0.analog-stereo \
    sink_master=alsa_output.platform-bcm2835_audio.analog-stereo \
    aec_method=webrtc \
    source_name=aec_source_hp \
    sink_name=aec_sink_hp

pactl set-default-source aec_source_hp
pactl set-default-sink aec_sink_hp
```

### Speaker bleed still happening

```bash
# Check that AEC is actually the default
pactl get-default-source  # must be aec_source_hp, not alsa_input...

# Check that the app's device ID is -1 (uses ALSA default)
grep input_device ~/minipupper-app/config/config.yaml

# Increase noise suppression (0→2)
pactl unload-module $(pactl list modules short | grep module-echo-cancel | awk '{print $1}')
pactl load-module module-echo-cancel ... aec_args="noise_suppression=2"
```

## Audio Manager Integration

The `audio_manager.py` reads config from `config.yaml`:

- `input_device: -1` → `sd.InputStream(device=None)` → ALSA default → PulseAudio → `aec_source_hp`
- `output_device: -1` → `sd.OutputStream(device=None)` → ALSA default → PulseAudio → `aec_sink_hp`

The barge-in detector continues running with VAD-based interruption, but
it now receives already-echo-cancelled audio from the AEC source. This
dramatically reduces false triggers from speaker bleed.

## Startup Sequence

1. **Boot** → systemd starts `pulseaudio-aec.service`
2. PulseAudio starts with `~/.config/pulse/default.pa`
3. `/etc/pulse/default.pa` loads ALSA auto-detection → discovers I2S mic and headphone jack
4. `module-echo-cancel` loads with `source_master=I2S mic`, `sink_master=headphone jack`
5. Default source/sink set to `aec_source_hp` / `aec_sink_hp`
6. Operator app starts → opens default ALSA device → routes through PulseAudio → gets echo-cancelled audio

## Version History

| Date | Change |
|------|--------|
| 2026-05-12 | Initial AEC setup with PulseAudio WebRTC module. Corrected sink from broken I2S codec output to working headphone jack. |
