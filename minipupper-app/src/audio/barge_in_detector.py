"""
Barge-in Detection Module
Detects user speech during TTS playback to enable interruption
Last Updated: 2026-05-09
"""

import logging
import numpy as np
import sounddevice as sd
import threading
from collections import deque
from dataclasses import dataclass
from typing import Optional, Callable

logger = logging.getLogger(__name__)


@dataclass
class BargeInConfig:
    """Configuration for barge-in detection"""
    enabled: bool = True
    min_energy_threshold: float = 500.0  # Audio energy threshold
    detection_timeout_ms: int = 500  # Time to wait for speech
    silence_duration_ms: int = 300  # Silence to confirm barge-in
    voice_activity_threshold: float = 0.5  # VAD confidence (0-1)
    sample_rate: int = 16000
    chunk_size: int = 512
    channels: int = 1
    input_device: int = -1


class BargeInDetector:
    """
    Detects user speech during TTS playback.
    
    Uses simple energy-based detection with optional VAD integration.
    When user speaks while robot is speaking, triggers interrupt callback.
    """
    
    def __init__(self, config: BargeInConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # State tracking
        self.is_listening = False
        self.speech_detected = False
        self.energy_history = deque(maxlen=10)
        self.silence_counter = 0
        
        # Threading
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        # Callbacks
        self.on_barge_in: Optional[Callable] = None
        
    def start_listening(self):
        """Start monitoring for barge-in"""
        if self.is_listening:
            return
            
        self.is_listening = True
        self.speech_detected = False
        self.silence_counter = 0
        self._stop_event.clear()
        
        self._thread = threading.Thread(target=self._detection_loop, daemon=True)
        self._thread.start()
        self.logger.debug("Barge-in detector started")
        
    def stop_listening(self):
        """Stop monitoring for barge-in"""
        if not self.is_listening:
            return
            
        self.is_listening = False
        self._stop_event.set()
        
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
            
        self.logger.debug("Barge-in detector stopped")
        
    def _detection_loop(self):
        """Main detection loop - runs in separate thread"""
        try:
            device = None if self.config.input_device < 0 else self.config.input_device
            stream = sd.InputStream(
                channels=self.config.channels,
                samplerate=self.config.sample_rate,
                blocksize=self.config.chunk_size,
                device=device,
                latency='low'
            )
            
            with stream:
                while self.is_listening and not self._stop_event.is_set():
                    try:
                        audio_chunk, _ = stream.read(self.config.chunk_size)
                        
                        # Compute energy
                        energy = np.sqrt(np.mean(audio_chunk ** 2))
                        self.energy_history.append(energy)
                        
                        # Check if speech energy exceeds threshold
                        if energy > self.config.min_energy_threshold:
                            self.silence_counter = 0
                            
                            if not self.speech_detected:
                                self.speech_detected = True
                                self.logger.info(
                                    f"Speech detected (energy: {energy:.1f})"
                                )
                                
                                # Trigger barge-in callback
                                if self.on_barge_in:
                                    self.on_barge_in()
                        else:
                            # Track silence
                            if self.speech_detected:
                                self.silence_counter += 1
                                silence_ms = (
                                    self.silence_counter * 
                                    self.config.chunk_size * 1000 / 
                                    self.config.sample_rate
                                )
                                
                                if silence_ms > self.config.silence_duration_ms:
                                    self.speech_detected = False
                                    self.logger.debug("Silence detected - reset")
                                    
                    except Exception as e:
                        self.logger.error(f"Error in detection loop: {e}")
                        
        except Exception as e:
            self.logger.error(f"Failed to initialize audio stream: {e}")
            
    def get_energy_level(self) -> float:
        """Get current audio energy level (0-1 normalized estimate)"""
        if not self.energy_history:
            return 0.0
        return min(1.0, np.mean(self.energy_history) / 1000.0)


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    config = BargeInConfig(enabled=True)
    detector = BargeInDetector(config)
    
    def on_interrupt():
        print(">>> BARGE-IN DETECTED! User interrupted TTS <<<")
    
    detector.on_barge_in = on_interrupt
    detector.start_listening()
    
    try:
        import time
        print("Listening for barge-in... Press Ctrl+C to stop")
        print("Try speaking while this is running")
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        detector.stop_listening()
