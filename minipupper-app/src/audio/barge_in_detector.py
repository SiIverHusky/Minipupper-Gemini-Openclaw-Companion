"""
Barge-in Detection Module
Detects user speech during TTS playback to enable interruption.
Last Updated: 2026-05-10
"""

import audioop
import logging
import threading
from collections import deque
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np
import sounddevice as sd

try:
    import webrtcvad
except ImportError:
    webrtcvad = None

logger = logging.getLogger(__name__)


@dataclass
class BargeInConfig:
    """Configuration for barge-in detection."""

    enabled: bool = True
    vad_aggressiveness: int = 2  # 0-3, higher is more aggressive
    detection_timeout_ms: int = 90  # Minimum voiced speech before triggering
    silence_duration_ms: int = 300  # Silence to confirm speech ended
    sample_rate: int = 16000
    frame_duration_ms: int = 30  # Must be 10, 20, or 30 for webrtcvad
    channels: int = 1
    input_device: int = -1
    aec_enabled: bool = True
    aec_max_delay_ms: int = 180  # Search window for playback-to-mic delay
    aec_max_gain: float = 1.2  # Max subtraction gain for reference echo
    aec_double_talk_ratio: float = 1.4  # Protect user speech when mic is much louder
    echo_suppression_threshold: float = 0.80  # Similarity threshold for suppressing playback echo
    echo_energy_ratio: float = 0.45  # Mic/playback energy ratio under which a voiced frame is likely echo
    nearend_min_cleaned_rms: float = 300.0  # Minimum cleaned RMS for near-end speech
    nearend_mic_to_playback_ratio: float = 1.15  # Mic must be louder than playback by this factor
    nearend_frames_required: int = 4  # Consecutive near-end speech frames to trigger
    startup_grace_ms: int = 300  # Ignore interrupts at TTS start while AEC aligns


class BargeInDetector:
    """Streaming WebRTC VAD for interrupting TTS on user speech."""

    def __init__(self, config: BargeInConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)

        if not webrtcvad:
            raise RuntimeError(
                "webrtcvad is required for streaming barge-in detection; install it first"
            )

        if self.config.channels != 1:
            self.logger.warning(
                "Barge-in VAD expects mono input; using first channel only when needed"
            )

        if self.config.frame_duration_ms not in (10, 20, 30):
            raise ValueError("frame_duration_ms must be 10, 20, or 30 for WebRTC VAD")

        self._vad = webrtcvad.Vad(int(self.config.vad_aggressiveness))
        self._playback_queue: deque[bytes] = deque(maxlen=12)
        self._frame_bytes = int(self.config.sample_rate * self.config.frame_duration_ms / 1000) * 2
        self._speech_frames_needed = max(1, int(self.config.detection_timeout_ms / self.config.frame_duration_ms))
        self._silence_frames_needed = max(1, int(self.config.silence_duration_ms / self.config.frame_duration_ms))
        self._max_delay_frames = max(1, int(self.config.aec_max_delay_ms / self.config.frame_duration_ms))

        self.is_listening = False
        self.speech_detected = False
        self.energy_history = deque(maxlen=10)

        self._speech_frames = 0
        self._silence_frames = 0
        self._nearend_frames = 0
        self._frames_since_start = 0
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self.on_barge_in: Optional[Callable[[], None]] = None

    def register_playback_frame(self, frame_bytes: bytes):
        """Register a chunk of far-end audio currently being played.

        This lets the detector suppress speech that is just speaker bleed.
        """
        if not frame_bytes:
            return

        if self.config.channels > 1:
            try:
                frame_bytes = audioop.tomono(frame_bytes, 2, 1.0, 0.0)
            except Exception:
                pass

        if len(frame_bytes) != self._frame_bytes:
            if len(frame_bytes) < self._frame_bytes:
                frame_bytes = frame_bytes + (b"\x00" * (self._frame_bytes - len(frame_bytes)))
            else:
                frame_bytes = frame_bytes[: self._frame_bytes]

        self._playback_queue.append(frame_bytes)

    def _is_likely_echo(self, mic_frame: bytes) -> bool:
        if not self._playback_queue:
            return False

        mic = np.frombuffer(mic_frame, dtype=np.int16).astype(np.float32)
        mic_energy = float(np.sqrt(np.mean(mic * mic))) if mic.size else 0.0
        if mic_energy <= 0.0:
            return False

        best_similarity = 0.0
        best_ratio = 0.0

        for playback_frame in list(self._playback_queue)[-4:]:
            playback = np.frombuffer(playback_frame, dtype=np.int16).astype(np.float32)
            if playback.size != mic.size or playback.size == 0:
                continue

            playback_energy = float(np.sqrt(np.mean(playback * playback)))
            if playback_energy <= 0.0:
                continue

            denom = float(np.linalg.norm(mic) * np.linalg.norm(playback))
            if denom <= 0.0:
                continue

            similarity = float(np.dot(mic, playback) / denom)
            ratio = mic_energy / playback_energy

            if similarity > best_similarity:
                best_similarity = similarity
                best_ratio = ratio

        return (
            best_similarity >= self.config.echo_suppression_threshold
            and best_ratio <= self.config.echo_energy_ratio
        )

    def _apply_reference_aec(self, mic_frame: bytes) -> bytes:
        """Apply lightweight in-app AEC using playback reference frames.

        This is not a full WebRTC AEC module, but it reduces speaker bleed by
        subtracting the best-aligned far-end frame from the mic frame.
        """
        if not self.config.aec_enabled or not self._playback_queue:
            return mic_frame

        mic = np.frombuffer(mic_frame, dtype=np.int16).astype(np.float32)
        if mic.size == 0:
            return mic_frame

        mic_energy = float(np.sqrt(np.mean(mic * mic)))
        if mic_energy <= 0.0:
            return mic_frame

        best_ref = None
        best_similarity = -1.0

        refs = list(self._playback_queue)[-self._max_delay_frames:]
        for ref_bytes in refs:
            ref = np.frombuffer(ref_bytes, dtype=np.int16).astype(np.float32)
            if ref.size != mic.size or ref.size == 0:
                continue

            ref_norm = float(np.linalg.norm(ref))
            mic_norm = float(np.linalg.norm(mic))
            if ref_norm <= 0.0 or mic_norm <= 0.0:
                continue

            similarity = float(np.dot(mic, ref) / (mic_norm * ref_norm))
            if similarity > best_similarity:
                best_similarity = similarity
                best_ref = ref

        if best_ref is None:
            return mic_frame

        ref_energy = float(np.sqrt(np.mean(best_ref * best_ref)))
        if ref_energy <= 0.0:
            return mic_frame

        # Double-talk protection: keep user speech dominant frames mostly intact.
        if mic_energy > ref_energy * float(self.config.aec_double_talk_ratio):
            return mic_frame

        denom = float(np.dot(best_ref, best_ref)) + 1e-6
        gain = float(np.dot(mic, best_ref) / denom)
        gain = max(0.0, min(float(self.config.aec_max_gain), gain))

        cleaned = mic - (gain * best_ref)
        cleaned = np.clip(cleaned, -32768.0, 32767.0).astype(np.int16)
        return cleaned.tobytes()

    def _playback_rms(self) -> float:
        if not self._playback_queue:
            return 0.0

        values = [float(audioop.rms(frame, 2)) for frame in list(self._playback_queue)[-4:]]
        return max(values) if values else 0.0

    def _nearend_gate(self, raw_frame: bytes, cleaned_frame: bytes) -> bool:
        cleaned_rms = float(audioop.rms(cleaned_frame, 2))
        if cleaned_rms < float(self.config.nearend_min_cleaned_rms):
            return False

        playback_rms = self._playback_rms()
        if playback_rms <= 1.0:
            return True

        mic_rms = float(audioop.rms(raw_frame, 2))
        return mic_rms >= playback_rms * float(self.config.nearend_mic_to_playback_ratio)

    def start_listening(self):
        """Start monitoring for barge-in."""
        if not self.config.enabled:
            self.logger.debug("Barge-in detector disabled by config")
            return

        if self.is_listening:
            return

        self.is_listening = True
        self.speech_detected = False
        self._speech_frames = 0
        self._silence_frames = 0
        self._nearend_frames = 0
        self._frames_since_start = 0
        self._stop_event.clear()
        self._playback_queue.clear()
        self.logger.debug("Barge-in detector armed")

    def stop_listening(self):
        """Stop monitoring for barge-in."""
        if not self.is_listening:
            return

        self.is_listening = False
        self._stop_event.set()

        self.logger.debug("Barge-in detector disarmed")

    def process_mic_frame(self, frame_bytes: bytes):
        """Process a microphone frame coming from the shared ASR input stream.

        The ASR pipeline remains the only reader of the physical mic. When
        barge-in is armed, this method consumes the same frames to detect near-end
        speech during TTS playback and trigger interruption.
        """
        if not self.is_listening or self._stop_event.is_set() or not frame_bytes:
            return

        if self.config.channels > 1:
            try:
                frame_bytes = audioop.tomono(frame_bytes, 2, 1.0, 0.0)
            except Exception:
                pass

        if len(frame_bytes) != self._frame_bytes:
            if len(frame_bytes) < self._frame_bytes:
                frame_bytes = frame_bytes + (b"\x00" * (self._frame_bytes - len(frame_bytes)))
            else:
                frame_bytes = frame_bytes[: self._frame_bytes]

        cleaned_frame = self._apply_reference_aec(frame_bytes)
        self._frames_since_start += 1

        self.energy_history.append(float(audioop.rms(cleaned_frame, 2)))

        # AEC-only mode: keep playback history and cleaned energy updated, but do
        # not trigger callbacks or interrupt TTS on VAD speech detection.
        if self._is_likely_echo(frame_bytes):
            self._silence_frames += 1
            return

        self._silence_frames = 0

    def get_energy_level(self) -> float:
        """Get current audio energy level (normalized estimate)."""
        if not self.energy_history:
            return 0.0
        return min(1.0, float(sum(self.energy_history)) / (len(self.energy_history) * 32768.0))


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    detector = BargeInDetector(BargeInConfig(enabled=True))

    def on_interrupt():
        print(">>> BARGE-IN DETECTED! User interrupted TTS <<<")

    detector.on_barge_in = on_interrupt
    detector.start_listening()

    try:
        import time

        print("Listening for barge-in... Press Ctrl+C to stop")
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        detector.stop_listening()
