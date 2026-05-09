"""
Audio Manager - Handles ASR and TTS with barge-in support
Supports multiple ASR engines (Google Cloud Speech, Whisper, etc.)
Last Updated: 2026-05-09
"""

import logging
import threading
import time
from typing import Optional, Callable
from dataclasses import dataclass
import io

try:
    from google.cloud import speech_v1, texttospeech
except ImportError:
    speech_v1 = None
    texttospeech = None

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None

import sounddevice as sd
import soundfile as sf
import numpy as np

from .barge_in_detector import BargeInDetector, BargeInConfig

logger = logging.getLogger(__name__)


@dataclass
class AudioConfig:
    sample_rate: int = 16000
    channels: int = 1
    input_device: int = -1
    output_device: int = -1
    asr_engine: str = "google"  # "google" or "whisper"
    asr_model: str = "base"  # For whisper fallback
    asr_device: str = "cpu"  # For whisper fallback
    tts_engine: str = "google"
    language_code: str = "en-US"


class AudioManager:
    """
    Unified audio manager handling:
    - Speech Recognition (ASR) with multiple engine support
    - Text-to-Speech (TTS)
    - Barge-in detection during speech playback
    """
    
    def __init__(self, config: AudioConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # ASR Setup - Google Cloud Speech preferred
        self.speech_client = None
        self.whisper_model = None
        
        if config.asr_engine == "google":
            if speech_v1:
                try:
                    self.speech_client = speech_v1.SpeechClient()
                    self.logger.info("✓ Google Cloud Speech-to-Text initialized")
                except Exception as e:
                    self.logger.error(f"Failed to initialize Google Speech: {e}")
                    self._fallback_to_whisper(config)
            else:
                self.logger.warning("google-cloud-speech not available")
                self._fallback_to_whisper(config)
        else:
            self._fallback_to_whisper(config)
        
        # TTS Setup
        self.tts_client = None
        if config.tts_engine == "google" and texttospeech:
            try:
                self.tts_client = texttospeech.TextToSpeechClient()
                self.logger.info("✓ Google Cloud TTS initialized")
            except Exception as e:
                self.logger.error(f"Failed to initialize Google TTS: {e}")
        
        # Barge-in Detection
        barge_in_config = BargeInConfig(
            sample_rate=config.sample_rate,
            input_device=config.input_device,
            channels=config.channels,
        )
        self.barge_in = BargeInDetector(barge_in_config)
        
        # State
        self._is_speaking = False
        self._speech_thread: Optional[threading.Thread] = None
        self._interrupt_event = threading.Event()
        
        # Callbacks
        self.on_speech_start: Optional[Callable] = None
        self.on_speech_end: Optional[Callable] = None
        self.on_interrupted: Optional[Callable] = None
    
    def _fallback_to_whisper(self, config: AudioConfig):
        """Fallback to Whisper if Google Cloud Speech unavailable"""
        if WhisperModel:
            try:
                self.whisper_model = WhisperModel(
                    config.asr_model,
                    device=config.asr_device,
                    compute_type="float32"
                )
                self.logger.info(f"✓ Whisper fallback initialized (model: {config.asr_model})")
            except Exception as e:
                self.logger.error(f"Failed to load Whisper model: {e}")
        else:
            self.logger.warning("No ASR engine available (faster-whisper not installed)")
        
    def transcribe_audio(self, audio_path: str) -> str:
        """
        Transcribe audio file to text using configured engine.
        
        Args:
            audio_path: Path to audio file
            
        Returns:
            Transcribed text
        """
        # Try Google Cloud Speech first
        if self.speech_client:
            try:
                return self._transcribe_google_cloud(audio_path)
            except Exception as e:
                self.logger.warning(f"Google Cloud Speech failed: {e}, falling back to Whisper")
        
        # Fallback to Whisper
        if self.whisper_model:
            try:
                return self._transcribe_whisper(audio_path)
            except Exception as e:
                self.logger.error(f"Transcription error: {e}")
                return ""
        
        self.logger.error("No ASR engine available")
        return ""
    
    def _transcribe_google_cloud(self, audio_path: str) -> str:
        """Transcribe using Google Cloud Speech-to-Text"""
        try:
            # Read audio file
            with open(audio_path, 'rb') as f:
                audio_content = f.read()
            
            # Prepare request
            audio = speech_v1.RecognitionAudio(content=audio_content)
            config = speech_v1.RecognitionConfig(
                encoding=speech_v1.RecognitionConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=self.config.sample_rate,
                language_code=self.config.language_code,
            )
            
            # Recognize speech
            response = self.speech_client.recognize(config=config, audio=audio)
            
            # Extract transcript
            transcript = ""
            for result in response.results:
                for alternative in result.alternatives:
                    transcript += alternative.transcript + " "
            
            return transcript.strip()
        except Exception as e:
            self.logger.error(f"Google Cloud Speech error: {e}")
            raise
    
    def _transcribe_whisper(self, audio_path: str) -> str:
        """Transcribe using Whisper model"""
        if not self.whisper_model:
            raise RuntimeError("Whisper model not loaded")
        
        segments, _ = self.whisper_model.transcribe(audio_path, language="en")
        text = " ".join([segment.text for segment in segments])
        return text.strip()
    
    def speak(self, text: str, voice_name: str = "en-US-Neural2-A") -> bool:
        """
        Speak text using TTS with barge-in support.
        
        Args:
            text: Text to speak
            voice_name: Google Cloud voice name
            
        Returns:
            True if speech completed, False if interrupted
        """
        if not self.tts_client:
            self.logger.warning("TTS not available, logging text: %s", text)
            return True
        
        try:
            # Generate speech
            synthesis_input = texttospeech.SynthesisInput(text=text)
            voice = texttospeech.VoiceSelectionParams(
                language_code="en-US",
                name=voice_name
            )
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.LINEAR16
            )
            
            response = self.tts_client.synthesize_speech(
                input=synthesis_input,
                voice=voice,
                audio_config=audio_config
            )
            
            # Play audio with barge-in monitoring
            return self._play_with_barge_in(response.audio_content)
            
        except Exception as e:
            self.logger.error(f"TTS error: {e}")
            return False
    
    def _play_with_barge_in(self, audio_data: bytes) -> bool:
        """
        Play audio while monitoring for barge-in.
        
        Args:
            audio_data: Audio bytes to play
            
        Returns:
            True if playback completed, False if interrupted
        """
        self._is_speaking = True
        self._interrupt_event.clear()
        
        # Notify listeners
        if self.on_speech_start:
            self.on_speech_start()
        
        # Start barge-in detection
        def on_interrupt():
            self.logger.info("Barge-in detected - interrupting speech")
            self._interrupt_event.set()
            if self.on_interrupted:
                self.on_interrupted()
        
        self.barge_in.on_barge_in = on_interrupt
        self.barge_in.start_listening()
        
        try:
            # Convert audio bytes to numpy array
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            audio_array = audio_array.astype(np.float32) / 32768.0
            
            # Play in chunks to allow interruption
            chunk_size = 4096
            for i in range(0, len(audio_array), chunk_size):
                if self._interrupt_event.is_set():
                    self.logger.info("Speech interrupted by user")
                    return False
                
                chunk = audio_array[i:i + chunk_size]
                sd.play(
                    chunk,
                    samplerate=self.config.sample_rate,
                    device=None if self.config.output_device < 0 else self.config.output_device,
                )
                # Brief wait before continuing (allows interrupt check)
                time.sleep(len(chunk) / self.config.sample_rate * 0.5)
            
            # Wait for playback to finish
            sd.wait()
            return not self._interrupt_event.is_set()
            
        except Exception as e:
            self.logger.error(f"Playback error: {e}")
            return False
        
        finally:
            self.barge_in.stop_listening()
            self._is_speaking = False
            
            if self.on_speech_end:
                self.on_speech_end()
    
    def shutdown(self):
        """Cleanup resources"""
        self.barge_in.stop_listening()
        sd.stop()
