#!/bin/bash
set -e

echo "=== PulseAudio AEC Startup ==="

if ! pactl info &>/dev/null; then
    echo "Starting PulseAudio..."
    pulseaudio --start
    sleep 1
fi

if ! pactl list sources short 2>/dev/null | grep -q aec_source_hp; then
    echo "Loading AEC module..."
    pactl load-module module-echo-cancel \
        source_master=alsa_input.platform-asoc-simple-card.0.analog-stereo \
        sink_master=alsa_output.platform-bcm2835_audio.analog-stereo \
        aec_method=webrtc \
        source_name=aec_source_hp \
        sink_name=aec_sink_hp \
        aec_args="analog_gain_control=0 digital_gain_control=1 noise_suppression=1" 2>/dev/null || true
    sleep 0.5
fi

pactl set-default-source aec_source_hp 2>/dev/null || true
pactl set-default-sink aec_sink_hp 2>/dev/null || true

echo "Source: $(pactl get-default-source 2>/dev/null)"
echo "Sink:   $(pactl get-default-sink 2>/dev/null)"

echo "=== Starting Minipupper Operator ==="
cd /home/ubuntu/minipupper-app
exec python3 minipupper_operator.py "$@"
