"""
Audio Manager - Handles ASR and TTS with barge-in support
Supports multiple ASR engines (Google Cloud Speech, Whisper, etc.)
Last Updated: 2026-05-10
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
    barge_in_enabled: bool = True
    barge_in_vad_aggressiveness: int = 2
    barge_in_detection_timeout_ms: int = 90
    barge_in_silence_duration_ms: int = 300
    barge_in_frame_duration_ms: int = 30
    barge_in_aec_enabled: bool = True
    barge_in_aec_max_delay_ms: int = 180
    barge_in_aec_max_gain: float = 1.2
    barge_in_aec_double_talk_ratio: float = 1.4
    barge_in_echo_suppression_threshold: float = 0.80
    barge_in_echo_energy_ratio: float = 0.45
    barge_in_nearend_min_cleaned_rms: float = 300.0
    barge_in_nearend_mic_to_playback_ratio: float = 1.15
    barge_in_nearend_frames_required: int = 4
    barge_in_startup_grace_ms: int = 300
    asr_engine: str = "google"  # "google" or "whisper"
    asr_model: str = "base"  # For whisper fallback
    asr_device: str = "cpu"  # For whisper fallback
    tts_engine: str = "google"
    language_code: str = "en-US"
    tts_speed: float = 1.0


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
            enabled=config.barge_in_enabled,
            vad_aggressiveness=config.barge_in_vad_aggressiveness,
            detection_timeout_ms=config.barge_in_detection_timeout_ms,
            silence_duration_ms=config.barge_in_silence_duration_ms,
            sample_rate=config.sample_rate,
            frame_duration_ms=config.barge_in_frame_duration_ms,
            input_device=config.input_device,
            channels=config.channels,
            aec_enabled=config.barge_in_aec_enabled,
            aec_max_delay_ms=config.barge_in_aec_max_delay_ms,
            aec_max_gain=config.barge_in_aec_max_gain,
            aec_double_talk_ratio=config.barge_in_aec_double_talk_ratio,
            echo_suppression_threshold=config.barge_in_echo_suppression_threshold,
            echo_energy_ratio=config.barge_in_echo_energy_ratio,
            nearend_min_cleaned_rms=config.barge_in_nearend_min_cleaned_rms,
            nearend_mic_to_playback_ratio=config.barge_in_nearend_mic_to_playback_ratio,
            nearend_frames_required=config.barge_in_nearend_frames_required,
            startup_grace_ms=config.barge_in_startup_grace_ms,
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
                audio_encoding=texttospeech.AudioEncoding.LINEAR16,
                speaking_rate=float(getattr(self.config, 'tts_speed', 1.0)),
                sample_rate_hertz=int(self.config.sample_rate),
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
            # Convert audio bytes (LINEAR16) to numpy float32 in range [-1,1]
            audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

            # Ensure correct shape for sounddevice (n_samples, channels)
            mono = audio_array.reshape(-1, 1)
            if self.config.channels == 1:
                frames = mono
            else:
                # replicate mono to multiple channels
                frames = np.tile(mono, (1, self.config.channels))

            device = None if self.config.output_device < 0 else int(self.config.output_device)

            # Temporarily set default device pair so other sd calls follow the same device
            prev_default = None
            try:
                prev_default = sd.default.device
            except Exception:
                prev_default = None

            try:
                if prev_default and isinstance(prev_default, (list, tuple)):
                    in_dev = prev_default[0]
                    out_dev = prev_default[1]
                else:
                    in_dev = None
                    out_dev = None

                if self.config.input_device >= 0:
                    in_dev = int(self.config.input_device)
                if self.config.output_device >= 0:
                    out_dev = int(self.config.output_device)

                try:
                    sd.default.device = (in_dev, out_dev)
                except Exception:
                    # ignore if device tuple invalid on this platform
                    pass

                # Use a single OutputStream to avoid pops/clicks from repeated stream starts
                with sd.OutputStream(samplerate=self.config.sample_rate,
                                     channels=self.config.channels,
                                     dtype='float32',
                                     device=device,
                                     latency='low') as stream:

                    frame_size = 4096
                    pos = 0
                    total = frames.shape[0]

                    while pos < total:
                        if self._interrupt_event.is_set():
                            self.logger.info("Speech interrupted by user")
                            try:
                                stream.stop()
                            except Exception:
                                pass
                            return False

                        end = min(pos + frame_size, total)
                        block = frames[pos:end]

                        try:
                            playback_pcm = np.clip(block * 32767.0, -32768, 32767).astype(np.int16)
                            vad_frame_samples = int(
                                self.config.sample_rate * self.config.barge_in_frame_duration_ms / 1000
                            )
                            vad_frame_samples = max(1, vad_frame_samples)

                            mono_pcm = playback_pcm[:, 0] if playback_pcm.ndim == 2 else playback_pcm
                            for i in range(0, mono_pcm.shape[0], vad_frame_samples):
                                chunk = mono_pcm[i:i + vad_frame_samples]
                                if chunk.size == 0:
                                    continue
                                self.barge_in.register_playback_frame(chunk.astype(np.int16).tobytes())
                        except Exception:
                            pass

                        stream.write(block)
                        pos = end

                    # ensure playback drains
                    try:
                        stream.stop()
                    except Exception:
                        pass

            finally:
                # restore previous default device
                try:
                    if prev_default is not None:
                        sd.default.device = prev_default
                except Exception:
                    pass

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
