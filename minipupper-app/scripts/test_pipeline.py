#!/usr/bin/env python3
"""Simple test harness: record or load audio, run ASR -> LLM -> TTS.

Usage:
  PYTHONPATH=. python3 scripts/test_pipeline.py --duration 5
  PYTHONPATH=. python3 scripts/test_pipeline.py --file examples/hello.wav

The script will:
 - load environment from config/.env (if present)
 - instantiate AudioManager and LLM provider
 - transcribe provided audio (or record from mic)
 - send transcript to LLM and print response
 - speak the response via TTS
"""

import argparse
import logging
import os
import sys
import tempfile
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

# Make project root importable so `from src...` works when running script directly
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import sounddevice as sd
import soundfile as sf
import numpy as np
import audioop

try:
    import webrtcvad
except Exception:
    webrtcvad = None

from src.audio.audio_manager import AudioManager, AudioConfig
from src.core.llm_engine import create_llm_provider, Message

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def load_env():
    if load_dotenv:
        here = os.path.dirname(__file__)
        env_paths = [
            os.path.join(here, '..', 'config', '.env'),
            os.path.join(here, '..', '..', '.env'),
        ]
        for p in env_paths:
            p = os.path.abspath(p)
            if os.path.exists(p):
                load_dotenv(p)
                logger.info(f"Loaded env from {p}")
                return
    logger.debug("No python-dotenv or no .env found; relying on process environment")


# Make project root importable so `from src...` works when running script directly


def record_wav(path: str, duration: int, samplerate: int, channels: int):
    logger.info(f"Recording {duration}s @ {samplerate}Hz channels={channels} ...")
    data = sd.rec(int(duration * samplerate), samplerate=samplerate, channels=channels, dtype='int16')
    sd.wait()
    sf.write(path, data, samplerate, subtype='PCM_16')
    logger.info(f"Saved recording to {path}")


def record_vad_wav(path: str, samplerate: int, channels: int,
                   vad_aggressiveness: int = 2,
                   speech_ms: int = 240,
                   silence_ms: int = 500,
                   min_capture_ms: int = 700,
                   max_record_ms: int = 15000):
    """Record to `path` using streaming WebRTC VAD.

    Starts after voiced speech is detected and stops after `silence_ms` of
    silence or when `max_record_ms` is reached.
    """
    if not webrtcvad:
        raise RuntimeError("webrtcvad is required for VAD recording")

    logger.info("Waiting for speech (streaming VAD)...")
    frame_duration_ms = 30
    blocksize = int(samplerate * frame_duration_ms / 1000)
    frame_bytes = blocksize * 2 * channels
    vad = webrtcvad.Vad(int(vad_aggressiveness))
    frames = []
    started = False
    speech_frames = 0
    silence_frames = 0
    speech_frames_needed = max(1, int(speech_ms / frame_duration_ms))
    silence_frames_needed = max(1, int(silence_ms / frame_duration_ms))
    min_capture_frames = max(1, int(min_capture_ms / frame_duration_ms))
    max_blocks = int(max_record_ms / frame_duration_ms)

    with sd.InputStream(
        samplerate=samplerate,
        channels=channels,
        blocksize=blocksize,
        dtype='int16',
    ) as stream:
        for _ in range(max_blocks):
            data, _ = stream.read(blocksize)
            pcm = data.tobytes()

            if channels > 1:
                pcm = audioop.tomono(pcm, 2, 1.0, 0.0)

            if len(pcm) != frame_bytes:
                if len(pcm) < frame_bytes:
                    pcm = pcm + (b'\x00' * (frame_bytes - len(pcm)))
                else:
                    pcm = pcm[:frame_bytes]

            is_speech = vad.is_speech(pcm, samplerate)

            if is_speech:
                speech_frames += 1
                if speech_frames >= speech_frames_needed:
                    if not started:
                        logger.info("Speech started")
                        started = True
                    silence_frames = 0
                    frames.append(np.frombuffer(pcm, dtype=np.int16).copy())
            elif started:
                silence_frames += 1
                frames.append(np.frombuffer(pcm, dtype=np.int16).copy())
                if silence_frames >= silence_frames_needed and len(frames) >= min_capture_frames:
                    logger.info("Silence threshold reached, stopping recording")
                    break

    if not frames:
        logger.info("No speech captured")
        return False

    # concatenate and write
    arr = np.concatenate(frames, axis=0)
    sf.write(path, arr, samplerate, subtype='PCM_16')
    logger.info(f"Saved VAD recording to {path}")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--file', '-f', help='Path to WAV file to transcribe')
    parser.add_argument('--duration', '-d', type=int, default=5, help='Seconds to record if no file provided')
    parser.add_argument('--record', action='store_true', help='Force recording from microphone')
    parser.add_argument('--continuous', action='store_true', help='Run repeatedly to test barge-in')
    args = parser.parse_args()

    load_env()

    # Build audio config from env or defaults
    sample_rate = int(os.getenv('MIC_SAMPLE_RATE', '16000'))
    channels = int(os.getenv('MIC_CHANNELS', '1'))
    input_device = int(os.getenv('MIC_DEVICE_INDEX', os.getenv('AUDIO_DEVICE_INDEX', '-1')))
    output_device = int(os.getenv('SPEAKER_DEVICE_INDEX', os.getenv('AUDIO_DEVICE_INDEX', '-1')))

    audio_cfg = AudioConfig(
        sample_rate=sample_rate,
        channels=channels,
        input_device=input_device,
        output_device=output_device,
        asr_engine=os.getenv('ASR_ENGINE', 'google'),
        asr_model=os.getenv('WHISPER_MODEL', 'base'),
        asr_device=os.getenv('WHISPER_DEVICE', 'cpu'),
        tts_engine=os.getenv('TTS_ENGINE', 'google'),
        language_code=os.getenv('LANGUAGE_CODE', 'en-US'),
    )

    am = AudioManager(audio_cfg)

    # LLM provider
    provider_name = os.getenv('LLM_PROVIDER', 'gemini')
    project_id = os.getenv('GOOGLE_CLOUD_PROJECT_ID')
    model = os.getenv('LLM_MODEL', 'gemini-2.5-flash')
    llm = create_llm_provider(provider_name=provider_name, project_id=project_id, model=model)

    def run_once(audio_file=None):
        if audio_file and not args.record:
            audio_path = audio_file
            tmp_created = False
        else:
            fd, tmp_path = tempfile.mkstemp(suffix='.wav')
            os.close(fd)
            # Try VAD-based recording first
            ok = record_vad_wav(
                tmp_path,
                sample_rate,
                channels,
                speech_ms=240,
                silence_ms=500,
                min_capture_ms=700,
                max_record_ms=args.duration * 1000,
            )
            if not ok:
                logger.info("VAD did not capture speech; falling back to fixed-duration recording")
                record_wav(tmp_path, args.duration, sample_rate, channels)
            audio_path = tmp_path
            tmp_created = True

        try:
            transcript = am.transcribe_audio(audio_path)
            logger.info(f"Transcript: {transcript}")

            if not transcript:
                logger.error("No transcript obtained; skipping")
                return

            messages = [Message(role='user', content=transcript)]
            response = llm.generate_response(messages)
            logger.info(f"LLM response: {response}")

            # Speak response (barge-in supported)
            completed = am.speak(response)
            if not completed:
                logger.info("Speech was interrupted by barge-in")

        finally:
            if tmp_created and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    # Continuous loop support for barge-in testing
    if args.continuous:
        logger.info("Starting continuous test loop. Press Ctrl+C to stop.")
        try:
            while True:
                run_once(args.file)
        except KeyboardInterrupt:
            logger.info("Continuous test loop stopped by user")
            return 0

    # Single run
    run_once(args.file)
    return 0


if __name__ == '__main__':
    sys.exit(main())
