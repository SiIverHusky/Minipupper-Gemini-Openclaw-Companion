#!/usr/bin/env python3
"""Continuous barge-in test harness.

Loop:
 - record short prompt from mic (or use --prompt text)
 - send transcript to LLM
 - expand/format LLM response into a long spoken paragraph
 - play response with barge-in enabled
 - if interrupted: immediately record short reply and continue

Usage:
  PYTHONPATH=. python3 scripts/test_bargein.py --duration 4 --record

Press Ctrl+C to stop.
"""

import os
import sys
import time
import tempfile
import logging
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

# Make project root importable
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.audio.audio_manager import AudioManager, AudioConfig
from src.core.llm_engine import create_llm_provider, Message
import sounddevice as sd
import soundfile as sf
import argparse

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def load_env():
    if load_dotenv:
        p = Path(__file__).resolve().parents[1] / 'config' / '.env'
        if p.exists():
            load_dotenv(p)
            logger.info(f"Loaded env from {p}")


def record_wav(path, duration, samplerate, channels):
    data = sd.rec(int(duration * samplerate), samplerate=samplerate, channels=channels, dtype='int16')
    sd.wait()
    sf.write(path, data, samplerate, subtype='PCM_16')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--duration', '-d', type=int, default=4, help='Seconds to record for prompts')
    parser.add_argument('--mic-sr', type=int, default=int(os.getenv('MIC_SAMPLE_RATE', '16000')))
    parser.add_argument('--channels', type=int, default=int(os.getenv('MIC_CHANNELS', '1')))
    parser.add_argument('--prompt', type=str, default=None, help='Optional fixed prompt text instead of recording')
    args = parser.parse_args()

    load_env()

    sample_rate = args.mic_sr
    channels = args.channels

    audio_cfg = AudioConfig(
        sample_rate=sample_rate,
        channels=channels,
        input_device=int(os.getenv('MIC_DEVICE_INDEX', os.getenv('AUDIO_DEVICE_INDEX', '-1'))),
        output_device=int(os.getenv('SPEAKER_DEVICE_INDEX', os.getenv('AUDIO_DEVICE_INDEX', '-1'))),
        asr_engine=os.getenv('ASR_ENGINE', 'google'),
        asr_model=os.getenv('WHISPER_MODEL', 'base'),
        asr_device=os.getenv('WHISPER_DEVICE', 'cpu'),
        tts_engine=os.getenv('TTS_ENGINE', 'google'),
        tts_speed=float(os.getenv('TTS_SPEED', '1.0')),
        language_code=os.getenv('LANGUAGE_CODE', 'en-US'),
    )

    am = AudioManager(audio_cfg)

    provider = os.getenv('LLM_PROVIDER', 'gemini')
    project_id = os.getenv('GOOGLE_CLOUD_PROJECT_ID')
    model = os.getenv('LLM_MODEL', 'gemini-2.5-flash')
    llm = create_llm_provider(provider_name=provider, project_id=project_id, model=model)

    logger.info('Starting continuous barge-in test. Press Ctrl+C to stop.')

    try:
        while True:
            if args.prompt:
                user_text = args.prompt
            else:
                fd, tmp = tempfile.mkstemp(suffix='.wav')
                os.close(fd)
                logger.info(f'Recording prompt for {args.duration}s...')
                record_wav(tmp, args.duration, sample_rate, channels)
                user_text = am.transcribe_audio(tmp)
                try:
                    os.remove(tmp)
                except Exception:
                    pass

            logger.info(f'User: {user_text}')

            if not user_text:
                logger.info('No input - retrying...')
                time.sleep(0.5)
                continue

            # Get LLM response
            messages = [Message(role='user', content=user_text)]
            resp = llm.generate_response(messages)
            logger.info(f'LLM (short): {resp}')

            # Make a longer version for testing interruption
            long_resp = (resp + ' ') * 12

            # Speak and allow interruption
            completed = am.speak(long_resp)
            if not completed:
                logger.info('Playback interrupted — recording quick follow-up (3s)')
                fd, tmp2 = tempfile.mkstemp(suffix='.wav')
                os.close(fd)
                record_wav(tmp2, 3, sample_rate, channels)
                follow = am.transcribe_audio(tmp2)
                try:
                    os.remove(tmp2)
                except Exception:
                    pass

                logger.info(f'Follow-up transcription: {follow}')
                if follow:
                    messages.append(Message(role='user', content=follow))
                    resp2 = llm.generate_response(messages)
                    logger.info(f'LLM follow-up: {resp2}')
                    am.speak(resp2)

            # Small pause between cycles
            time.sleep(0.5)

    except KeyboardInterrupt:
        logger.info('Stopped by user')


if __name__ == '__main__':
    main()
