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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--file', '-f', help='Path to WAV file to transcribe')
    parser.add_argument('--duration', '-d', type=int, default=5, help='Seconds to record if no file provided')
    parser.add_argument('--record', action='store_true', help='Force recording from microphone')
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

    # Prepare audio file
    if args.file and not args.record:
        audio_path = args.file
    else:
        fd, tmp_path = tempfile.mkstemp(suffix='.wav')
        os.close(fd)
        record_wav(tmp_path, args.duration, sample_rate, channels)
        audio_path = tmp_path

    try:
        transcript = am.transcribe_audio(audio_path)
        logger.info(f"Transcript: {transcript}")

        if not transcript:
            logger.error("No transcript obtained; aborting")
            return 2

        messages = [Message(role='user', content=transcript)]
        response = llm.generate_response(messages)
        logger.info(f"LLM response: {response}")

        # Speak response
        am.speak(response)

    finally:
        if 'tmp_path' in locals() and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass

    return 0


if __name__ == '__main__':
    sys.exit(main())
