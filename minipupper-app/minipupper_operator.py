"""
Minipupper Operator - Main Application
Autonomous Operator role with robust capabilities
Last Updated: 2026-05-10
"""

import json
import logging
import os
import sys
import yaml
import threading
from pathlib import Path
from typing import Dict, Any, Optional
import time
import re
import argparse
from dataclasses import dataclass, field

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

from src.core.task_queue import (
    input_text_queue, output_text_queue,
    speech_active, movement_queue, status_queue, control_queue
)
from src.core.task_queue import openclaw_queue
from src.audio.audio_manager import AudioManager, AudioConfig
from src.audio.barge_in_detector import BargeInConfig
from src.core.llm_engine import create_llm_provider, Message
from src.core.task_watcher import TaskWatcher
from src.openclaw.client import OpenClawClient, load_device_identity

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MinipupperOperator:
    """
    Main operator for Minipupper robot.
    
    Responsibilities:
    - Conversational interaction with user
    - Direct robot control (no OpenClaw dependency)
    - Audio I/O with barge-in support
    - Task execution and movement
    """
    
    def __init__(self, config_path: str = "config/config.yaml", keyboard: bool = False, mute: bool = False):
        """
        Initialize operator.
        
        Args:
            config_path: Path to configuration YAML file
        """
        self.logger = logger

        self._load_environment(config_path)
        self.config = self._load_config(config_path)
        
        # Audio system (Google Cloud Speech-to-Text + TTS with barge-in)
        audio_settings = self.config.get('audio', {})
        asr_settings = audio_settings.get('asr', {})
        tts_settings = audio_settings.get('tts', {})
        barge_in_settings = self.config.get('barge_in', {})
        default_audio_device = self._get_int_setting('AUDIO_DEVICE_INDEX', -1)
        input_device = self._get_int_setting(
            'MIC_DEVICE_INDEX',
            default_audio_device,
        )
        output_device = self._get_int_setting(
            'SPEAKER_DEVICE_INDEX',
            default_audio_device,
        )
        audio_config = AudioConfig(
            sample_rate=self._get_int_setting(
                'MIC_SAMPLE_RATE',
                asr_settings.get('sample_rate', 16000),
            ),
            channels=self._get_int_setting(
                'MIC_CHANNELS',
                audio_settings.get('channels', 1),
            ),
            input_device=input_device,
            output_device=output_device,
            barge_in_enabled=bool(barge_in_settings.get('enabled', True)),
            barge_in_vad_aggressiveness=self._get_int_setting(
                'BARGE_IN_VAD_AGGRESSIVENESS',
                barge_in_settings.get('vad_aggressiveness', 2),
            ),
            barge_in_detection_timeout_ms=self._get_int_setting(
                'BARGE_IN_DETECTION_TIMEOUT_MS',
                barge_in_settings.get('detection_timeout_ms', 90),
            ),
            barge_in_silence_duration_ms=self._get_int_setting(
                'BARGE_IN_SILENCE_DURATION_MS',
                barge_in_settings.get('silence_duration_ms', 300),
            ),
            barge_in_frame_duration_ms=self._get_int_setting(
                'BARGE_IN_FRAME_DURATION_MS',
                barge_in_settings.get('frame_duration_ms', 30),
            ),
            barge_in_aec_enabled=bool(barge_in_settings.get('aec_enabled', True)),
            barge_in_aec_max_delay_ms=self._get_int_setting(
                'BARGE_IN_AEC_MAX_DELAY_MS',
                barge_in_settings.get('aec_max_delay_ms', 180),
            ),
            barge_in_aec_max_gain=float(os.getenv(
                'BARGE_IN_AEC_MAX_GAIN',
                barge_in_settings.get('aec_max_gain', 1.2),
            )),
            barge_in_aec_double_talk_ratio=float(os.getenv(
                'BARGE_IN_AEC_DOUBLE_TALK_RATIO',
                barge_in_settings.get('aec_double_talk_ratio', 1.4),
            )),
            barge_in_echo_suppression_threshold=float(os.getenv(
                'BARGE_IN_ECHO_SUPPRESSION_THRESHOLD',
                barge_in_settings.get('echo_suppression_threshold', 0.80),
            )),
            barge_in_echo_energy_ratio=float(os.getenv(
                'BARGE_IN_ECHO_ENERGY_RATIO',
                barge_in_settings.get('echo_energy_ratio', 0.45),
            )),
            barge_in_nearend_min_cleaned_rms=float(os.getenv(
                'BARGE_IN_NEAREND_MIN_CLEANED_RMS',
                barge_in_settings.get('nearend_min_cleaned_rms', 300.0),
            )),
            barge_in_nearend_mic_to_playback_ratio=float(os.getenv(
                'BARGE_IN_NEAREND_MIC_TO_PLAYBACK_RATIO',
                barge_in_settings.get('nearend_mic_to_playback_ratio', 1.15),
            )),
            barge_in_nearend_frames_required=self._get_int_setting(
                'BARGE_IN_NEAREND_FRAMES_REQUIRED',
                barge_in_settings.get('nearend_frames_required', 4),
            ),
            barge_in_startup_grace_ms=self._get_int_setting(
                'BARGE_IN_STARTUP_GRACE_MS',
                barge_in_settings.get('startup_grace_ms', 300),
            ),
            asr_engine=os.getenv('ASR_ENGINE', asr_settings.get('engine', 'google')),
            asr_model=os.getenv('WHISPER_MODEL', asr_settings.get('model', 'base')),
            asr_device=os.getenv('WHISPER_DEVICE', asr_settings.get('device', 'cpu')),
            tts_engine=tts_settings.get('engine', 'google'),
            tts_speed=float(os.getenv('TTS_SPEED', tts_settings.get('speed', 1.0))),
            language_code=asr_settings.get('language', 'en-US'),
        )
        self.audio_manager = AudioManager(audio_config)
        
        # Phase 2: Load the enhanced system prompt that enables task offloading
        phase2_prompt_path = os.path.join(
            os.path.dirname(config_path), "system_prompt_phase2.txt"
        )
        phase2_prompt = None
        if os.path.exists(phase2_prompt_path):
            try:
                with open(phase2_prompt_path) as f:
                    phase2_prompt = f.read()
                self.logger.info("Loaded Phase 2 system prompt from %s", phase2_prompt_path)
            except Exception as e:
                self.logger.warning("Could not load Phase 2 prompt: %s", e)
        
        # LLM Engine (Gemini via Vertex AI)
        self.llm = create_llm_provider(
            provider_name=self.config.get('operator', {}).get('llm_provider', 'gemini'),
            project_id=os.getenv('GOOGLE_CLOUD_PROJECT_ID'),
            model=self.config.get('operator', {}).get('llm_model', 'gemini-1.5-flash'),
            system_prompt=phase2_prompt,
        )
        
        # Phase 2: File-based task watcher for agent communication
        # Use a dedicated LLM provider for announcements to avoid thread contention
        # with the main operator thread. A simpler system prompt is fine here.
        self.announce_llm = create_llm_provider(
            provider_name=self.config.get('operator', {}).get('llm_provider', 'gemini'),
            project_id=os.getenv('GOOGLE_CLOUD_PROJECT_ID'),
            model=self.config.get('operator', {}).get('llm_model', 'gemini-1.5-flash'),
            system_prompt=(
                "You are a concise status announcer for a robot assistant. "
                "Keep responses under 2 sentences. Sound natural and helpful. "
                "Speak as if you are the robot itself."
            ),
        )
        # State
        self.is_running = False
        self.current_state = "idle"
        self.conversation_history = []
        self._task_results_lock = threading.Lock()
        self.task_watcher = TaskWatcher(
            llm=self.llm,
            announce_llm=self.announce_llm,
            audio_manager=self.audio_manager,
            on_result=self._on_task_result,
        )

        # Phase 3: Pre-inject existing implementations into conversation history
        # so Gemini knows what is already built on first turn
        try:
            _idx_path = os.path.expanduser("~/minipupper-app/knowledge/INDEX.json")
            if os.path.exists(_idx_path):
                with open(_idx_path) as _f:
                    _index = json.load(_f)
                _existing = []
                for _topic, _info in _index.items():
                    _impls = _info.get("implementations", [])
                    for _impl in _impls:
                        _impl_path = os.path.expanduser("~/minipupper-app/custom/" + _impl + "/test_results.md")
                        _tested = os.path.exists(_impl_path)
                        _summary = _info.get("summary", _topic)
                        _existing.append("- " + _impl + ": " + _summary + " [tested=" + str(_tested) + "]")
                if _existing:
                    _lines = "\n".join(_existing)
                    _text = "Existing implementations loaded from knowledge base:\n" + _lines
                    self.conversation_history.append(Message(role="system", content=_text))
                    self.logger.info("Phase 3: Pre-injected %d existing implementations into conversation history", len(_existing))
        except Exception as _e:
            self.logger.warning("Phase 3: Failed to pre-inject knowledge: %s", _e)
        self.checkpoint = None
        
        # CLI flags
        self.keyboard_mode = keyboard
        self.mute_mode = mute
        # Always set volume on startup: 0% if muted, 100% otherwise
        # (PulseAudio sink volume persists between runs)
        self._set_mute_volume()
        
        # Thread pool
        self._worker_threads = []
        self._stop_event = threading.Event()
        self._interrupt_requested = threading.Event()
        self.gateway_client: Optional[OpenClawClient] = None
        
        # Phase 2: Track start time for filtering stale gateway messages
        self._started_at = time.time()
        self._agent_session = self.config.get("network", {}).get("session_target", None)
        self._cron_job_id = self.config.get("network", {}).get("cron_job_id", "")
        
        self.logger.info("Minipupper Operator initialized")
        
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load YAML configuration file"""
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            self.logger.error(f"Config file not found: {config_path}")
            raise
        except yaml.YAMLError as e:
            self.logger.error(f"Invalid YAML config: {e}")
            raise

    def _load_environment(self, config_path: str):
        """Load environment variables from repo-local .env files if present."""
        if not load_dotenv:
            self.logger.warning("python-dotenv not available; skipping .env loading")
            return

        config_file = Path(config_path).resolve()
        env_files = [
            config_file.parent.parent / ".env",
            config_file.parent / ".env",
        ]

        for env_file in env_files:
            if env_file.exists():
                load_dotenv(dotenv_path=env_file, override=False)
                self.logger.info(f"Loaded environment from {env_file}")

    def _get_int_setting(self, name: str, default: int) -> int:
        """Read an integer environment variable with a safe fallback."""
        value = os.getenv(name)
        if value is None or value == "":
            return int(default)

        try:
            return int(value)
        except ValueError:
            self.logger.warning(f"Invalid integer for {name}: {value!r}; using {default}")
            return int(default)
    
    def start(self):
        """Start the operator"""
        if self.is_running:
            self.logger.warning("Operator already running")
            return
        
        self.is_running = True
        self._stop_event.clear()
        
        # Start worker threads
        self._start_workers()
        
        # Phase 2: Start file-based task watcher
        if hasattr(self, 'task_watcher') and self.task_watcher:
            self.task_watcher.start()
        
        self.logger.info("Minipupper Operator started")
        self._broadcast_status("Operator ready")
    
    def stop(self):
        """Stop the operator gracefully"""
        if not self.is_running:
            return
        
        self.is_running = False
        self._stop_event.set()
        
        # Wait for workers
        for thread in self._worker_threads:
            thread.join(timeout=5.0)
        
        self.audio_manager.shutdown()
        # Phase 2: Stop task watcher
        if hasattr(self, 'task_watcher') and self.task_watcher:
            self.task_watcher.stop()
        
        self.logger.info("Minipupper Operator stopped")
    
    def _start_workers(self):
        """Start background worker threads"""
        # Speech-to-text worker (or keyboard input worker)
        if self.keyboard_mode:
            kbd_thread = threading.Thread(
                target=self._keyboard_worker,
                daemon=True,
                name="KeyboardWorker"
            )
            kbd_thread.start()
            self._worker_threads.append(kbd_thread)
        else:
            asr_thread = threading.Thread(
                target=self._asr_worker,
                daemon=True,
                name="ASRWorker"
            )
            asr_thread.start()
            self._worker_threads.append(asr_thread)
        
        # Operator Worker - processes input and generates responses
        op_thread = threading.Thread(
            target=self._operator_worker,
            daemon=True,
            name="OperatorWorker"
        )
        op_thread.start()
        self._worker_threads.append(op_thread)
        
        # Movement Worker - executes movement commands
        move_thread = threading.Thread(
            target=self._movement_worker,
            daemon=True,
            name="MovementWorker"
        )
        move_thread.start()
        self._worker_threads.append(move_thread)
        
        # Control Worker - handles system commands
        control_thread = threading.Thread(
            target=self._control_worker,
            daemon=True,
            name="ControlWorker"
        )
        control_thread.start()
        self._worker_threads.append(control_thread)

        # Gateway Worker - connect to OpenClaw Gateway and receive snapshots
        gw_thread = threading.Thread(
            target=self._gateway_worker,
            daemon=True,
            name="GatewayWorker"
        )
        gw_thread.start()
        self._worker_threads.append(gw_thread)
    
    def _asr_worker(self):
        """Worker: Speech-to-text processing"""
        self.logger.info("ASR Worker started")
        
        while self.is_running:
            try:
                # Continuously listen for speech
                transcript = self.audio_manager.listen()
                
                if transcript and transcript.strip():
                    self.logger.info(f"ASR: {transcript}")

                    # Explicit interrupt commands (user telling the robot to stop)
                    try:
                        if self._is_interrupt_command(transcript):
                            self.logger.info("Interrupt command detected from ASR: %s", transcript)
                            # Signal audio manager to stop playback immediately
                            try:
                                self.audio_manager.interrupt_speech()
                            except Exception:
                                pass
                            # mark internal interrupt flag for any other consumers
                            try:
                                self._interrupt_requested.set()
                            except Exception:
                                pass
                            # Do not enqueue interrupt phrases as user input
                            continue
                    except Exception:
                        pass

                    # If currently speaking, and the transcript is not speaker-bleed,
                    # treat this as user speech and interrupt playback so the user can take over.
                    try:
                        speaking = getattr(self.audio_manager, '_is_speaking', False)
                        if speaking and not self._is_likely_speaker_bleed(transcript):
                            self.logger.info("User speech detected during playback — interrupting: %s", transcript)
                            try:
                                self.audio_manager.interrupt_speech()
                            except Exception:
                                pass
                            try:
                                self._interrupt_requested.set()
                            except Exception:
                                pass
                            # Continue to enqueue the user transcript for processing
                    except Exception:
                        pass

                    # Detect speaker-bleed: if the transcript is essentially verbatim
                    # from the last assistant response, drop it to avoid treating
                    # the robot's own speech as user input.
                    try:
                        if self._is_likely_speaker_bleed(transcript):
                            self.logger.debug("Dropped ASR transcript (likely speaker-bleed): %s", transcript)
                            continue
                    except Exception:
                        # If bleed detection fails for any reason, fallback to enqueue
                        pass

                    input_text_queue.put(transcript)
                        
            except Exception as e:
                self.logger.error(f"ASR Worker error: {e}")
                time.sleep(1.0)
    
    def _keyboard_worker(self):
        """Worker: Keyboard input (replaces ASR in --keyboard mode)"""
        self.logger.info("Keyboard Worker started")
        print()
        print("=" * 60)
        print("  KEYBOARD INPUT MODE")
        print("  " + "-" * 54)
        print("  Type your message below and press Enter.")
        print("  Type 'exit' or 'quit' to stop the operator.")
        print("  Type 'mute' to toggle TTS on/off (if started with --mute).")
        print("=" * 60)
        print()

        while self.is_running:
            try:
                user_input = input("> ")
                if user_input.strip().lower() in ("exit", "quit"):
                    self.logger.info("Exit requested via keyboard")
                    self.is_running = False
                    break
                if user_input.strip().lower() == "mute":
                    self.mute_mode = not self.mute_mode
                    self._set_mute_volume()
                    status = "OFF" if self.mute_mode else "ON"
                    print(f"[Mute mode is now {status}]")
                    continue
                if user_input.strip():
                    input_text_queue.put(user_input.strip())
            except EOFError:
                break
            except KeyboardInterrupt:
                break
            except Exception as e:
                self.logger.error(f"Keyboard Worker error: {e}")
                time.sleep(0.5)
    
    def _operator_worker(self):
        """Worker: Process input and generate responses"""
        self.logger.info("Operator Worker started")
        
        while self.is_running:
            try:
                # Check for input text
                try:
                    text = input_text_queue.get(timeout=1.0)
                except Exception:
                    continue

                self.logger.info(f"Operator processing: {text}")
                self.current_state = "processing"
                self._broadcast_status("Processing your request...")

                # Phase 3: Drain any completed task results into conversation history,
                # so Gemini knows what happened and can follow up properly.
                # (Note: _on_task_result may add during processing, but the lock
                #  and the fact that the watcher runs on a delay means this is fine.)
                # (Already injected asynchronously by _on_task_result callback.)

                # Phase 2: Always process through Gemini LLM first
                # Gemini decides whether to handle locally or offload to agent
                response = self._process_user_input(text)
                
                # Phase 2: Check if Gemini wants to offload one or more tasks to the OpenClaw agent.
                spoken_text, task_payloads = self._extract_task_blocks(response)
                if task_payloads:
                    self.logger.info("Phase 2: Offloading %d task(s) to agent", len(task_payloads))
                    if not spoken_text:
                        spoken_text = "I'll handle that now."
                    # Write all pending tasks first, then trigger cron once for the full batch.
                    if hasattr(self, 'task_watcher') and self.task_watcher:
                        self.task_watcher.write_tasks(task_payloads)
                        self.logger.info("Phase 2: Wrote %d task(s) to tasks.json for agent", len(task_payloads))
                        if self.gateway_client and self.gateway_client.is_connected:
                            cron_id = getattr(self, "_cron_job_id", "")
                            if cron_id:
                                self.gateway_client.trigger_cron(cron_id)
                                self.logger.info("Phase 2: Triggered cron %s for %d task(s)", cron_id, len(task_payloads))
                            else:
                                self.gateway_client.send_sessions_send(
                                    getattr(self, "_agent_session", "") or "main",
                                    "task_written"
                                )
                                self.logger.info("Phase 2: Notified agent via main session")

                        # Speak introductory text once before the task batch executes.
                        if spoken_text:
                            output_text_queue.put(spoken_text)
                            try:
                                completed = self.audio_manager.speak(spoken_text)
                                if not completed:
                                    self.logger.info("Speech interrupted")
                            except Exception:
                                pass
                        self.current_state = "idle"
                        continue
                
                # Fallback: No offload or failed to send — speak Gemini's response locally
                
                if response:
                    # Log generated response text at INFO so operator output is visible
                    try:
                        self.logger.info("Generated response (%d chars): %s", len(response), response)
                    except Exception:
                        # Fallback if message too large for formatting
                        self.logger.info("Generated response (%d chars)", len(response))
                    output_text_queue.put(response)
                    
                    # Speak response with barge-in support
                    try:
                        interrupted = not self.audio_manager.speak(response)
                        if interrupted:
                            self.logger.info("Speech playback stopped")
                            self._broadcast_status("Speech playback stopped")
                    except Exception as e:
                        self.logger.error(f"TTS Error: {e}")
                
                self.current_state = "idle"
                    
            except Exception as e:
                self.logger.error(f"Operator Worker error: {e}")
                self.current_state = "idle"
                time.sleep(0.5)

    def _gateway_worker(self):
        """Worker: maintain connection to OpenClaw Gateway and forward frames."""
        self.logger.info("Gateway Worker started")
        network_cfg = self.config.get('network', {})
        if not network_cfg.get('tailscale_enabled', False):
            self.logger.info("Tailscale disabled; skipping Gateway Worker")
            return

        gateway_url = os.getenv('OPENCLAW_GATEWAY_URL') or network_cfg.get('gateway_url')
        if not gateway_url:
            self.logger.warning("No gateway_url configured; skipping Gateway Worker")
            return

        # Load device identity if available
        device_identity = load_device_identity()
        # Phase 2: Determine agent session from config
        self._agent_session = self.config.get('network', {}).get('session_target', None)
        if self._agent_session:
            self.logger.info("Phase 2: Agent session target: %s", self._agent_session)
        self.gateway_client = OpenClawClient(
            gateway_url,
            device_identity=device_identity,
            session_target=self._agent_session or 'main',
        )

        def handler(frame: dict):
            try:
                openclaw_queue.put(frame, timeout=0.1)
            except Exception:
                pass

        try:
            try:
                self.gateway_client.start(handler)
            except Exception as e:
                # Likely missing dependency (websocket-client) or startup failure.
                # Log once and disable gateway integration without crashing the thread.
                logger.warning(f"Gateway client could not start: {e}")
                self.gateway_client = None
                return

            # keep alive until stop requested
            while self.is_running and not self._stop_event.is_set():
                # Drain openclaw frames and make lightweight decisions here
                try:
                    frame = openclaw_queue.get(timeout=1.0)
                except Exception:
                    continue

                try:
                    self._handle_openclaw_frame(frame)
                except Exception:
                    continue

        finally:
            if self.gateway_client:
                self.gateway_client.stop()

    @dataclass
    class Checkpoint:
        phase: str = ""
        last_transcript: str = ""
        last_agent_response: str = ""
        last_agent_response_at: float = 0.0
        last_status_announced: str = ""
        last_status_at: float = 0.0
        agent_processing_started_at: float = 0.0
        agent_processing_seconds: float = 0.0
        pending_barge_in: bool = False
        error_count: int = 0
        gateway_connected: bool = False
        last_gateway_disconnect_at: float = 0.0
        progress: float = 0.0
        raw: dict = field(default_factory=dict)

    def _is_significant_update(self, old: Optional['MinipupperOperator.Checkpoint'], new: 'MinipupperOperator.Checkpoint') -> bool:
        """Decide whether new checkpoint represents a significant update to announce.

        Heuristic: phase change, progress increased >=10%, or status text changed.
        Completion (progress>=100 or phase=="finished") is always significant.
        """
        if old is None:
            return True

        if new.phase and new.phase != old.phase:
            return True

        # completion
        if (new.phase and new.phase.lower() in ("finished", "complete", "done")) or new.progress >= 100.0:
            if old.progress < 100.0:
                return True

        # progress jump
        try:
            if new.progress - old.progress >= 10.0:
                return True
        except Exception:
            pass

        # status text changed
        if new.last_agent_response and new.last_agent_response != old.last_agent_response:
            return True

        return False

    def _handle_openclaw_frame(self, frame: dict):
        """Process raw frame from OpenClaw Gateway and potentially announce via LLM.

        Phase 2: Before falling back to freeform parsing, check for structured
        minipupper-v1 protocol messages. If found, use the protocol handler
        for clean status/result extraction.

        Phase 2b: Only process protocol messages from 'assistant' role that
        are actual task results, not internal cron chatter.
        """
        # Phase 2b: Skip messages from 'user' role (our own task sends echo back)
        if frame.get('event') == 'session.message':
            msg_role = frame.get('payload', {}).get('message', {}).get('role', '')
            msg_content = frame.get('payload', {}).get('message', {}).get('content', '')
            if msg_role == 'user':
                return  # Don't process our own messages echoing back
        # Phase 2: Try structured protocol first
            # Phase 2c: Skip cron session chatter — file-based protocol only
            session_key = frame.get("payload", {}).get("sessionKey", "")
            if ":cron:" in session_key:
                return
        try:
            from src.core.protocol_handler import handle_protocol_frame
            announcement = handle_protocol_frame(frame, self.llm, started_at=self._started_at)
            if announcement:
                self.logger.info("Gateway response: %s", announcement[:200])
                return
        except Exception:
            pass

        # Phase 2d: No legacy fallback — file-based protocol only; the file
        # handles everything.
        return

        # Legacy fallback: Build a minimal checkpoint from the frame
        # Phase 2: Skip stale messages (older than 120s before startup)
        if hasattr(self, '_started_at'):
            msg_ts = frame.get('payload', {}).get('message', {}).get('timestamp', 0)
            if msg_ts and msg_ts < self._started_at:
                return
        cp = MinipupperOperator.Checkpoint()
        cp.raw = frame
        cp.gateway_connected = True
        cp.last_status_at = time.time()

        # Try to extract common fields
        payload = frame.get('payload', {}) if isinstance(frame, dict) else {}
        # session.message -> assistant content
        if frame.get('event') == 'session.message':
            msg = payload.get('message', {})
            role = msg.get('role')
            content = msg.get('content')
            if role == 'assistant' and content:
                cp.last_agent_response = content
                # try to detect progress like "progress: 42%" or numeric
                # naive parse: look for pattern "%" in content
                try:
                    if '%' in content:
                        # extract first number before %
                        import re
                        m = re.search(r"(\d{1,3})%", content)
                        if m:
                            cp.progress = float(m.group(1))
                except Exception:
                    pass

        # Some frames may include explicit status/progress fields
        if isinstance(payload, dict):
            if 'status' in payload:
                cp.last_agent_response = str(payload.get('status'))
            if 'progress' in payload:
                try:
                    cp.progress = float(payload.get('progress') or 0.0)
                except Exception:
                    pass
            if 'phase' in payload:
                cp.phase = str(payload.get('phase'))

        significant = self._is_significant_update(self.checkpoint, cp)
        # update stored checkpoint
        self.checkpoint = cp

        if not significant:
            return

        # Build an announcement via LLM to be concise and friendly
        try:
            prompt = [
                Message(role='system', content='You are a concise status announcer for a robot operator.'),
                Message(role='user', content=f"Summarize this status update briefly for a user: {cp.last_agent_response or cp.phase or cp.progress}")
            ]
            announcement = self.llm.generate_response(messages=prompt, max_tokens=80)
        except Exception:
            pass
            # Phase 2d: No legacy fallback — file-based protocol only
            return
            # Fallback to raw text
            if cp.last_agent_response:
                announcement = cp.last_agent_response
            elif cp.phase:
                announcement = f"Task phase: {cp.phase}"
            else:
                announcement = f"Progress: {cp.progress}%"

        # Keep Gateway updates as logs only.
        # TTS should speak only direct LLM output from user interactions.
        try:
            self.logger.info("Gateway response: %s", announcement[:200])
        except Exception as e:
            self.logger.error("Error handling Gateway response: %s", e)
    
    def _movement_worker(self):
        """Worker: Execute movement commands"""
        self.logger.info("Movement Worker started")
        
        while self.is_running:
            try:
                # Check for movement commands
                try:
                    command = movement_queue.get(timeout=1.0)
                except:
                    continue
                
                # Execute movement
                self._execute_movement(command)
                
            except Exception as e:
                self.logger.error(f"Movement Worker error: {e}")
    
    def _control_worker(self):
        """Worker: Handle system control commands"""
        self.logger.info("Control Worker started")
        
        while self.is_running:
            try:
                # Check for control commands
                try:
                    command = control_queue.get(timeout=1.0)
                except:
                    continue
                
                if command == "shutdown":
                    self.logger.info("Shutdown command received")
                    self.stop()
                elif command == "restart":
                    self.logger.info("Restart command received")
                    self.stop()
                    self.start()
                    
            except Exception as e:
                self.logger.error(f"Control Worker error: {e}")

    
    def _on_task_result(self, task: dict):
        """Called by TaskWatcher when a task completes and is announced.
        Injects the result into Gemini's conversation history so it knows
        what happened on subsequent turns."""
        action = task.get("action", "unknown")
        result = task.get("result", "")
        error = task.get("error")
        user_query = task.get("userQuery", "")
        if error:
            text = f"[Task completed: {action}] Error: {error}"
        else:
            text = f"[Task completed: {action}] Result: {result}"
        with self._task_results_lock:
            self.conversation_history.append(Message(role="system", content=text))
        self.logger.info("Phase 3: Injected task result into conversation history: %s", action)

    def _process_user_input(self, text: str) -> str:
        """
        Process user input and generate response using Gemini LLM.
        
        Args:
            text: User input text
            
        Returns:
            Response text to speak
        """
        self.logger.info(f"Processing input: {text}")
        self.current_state = "processing"
        
        try:
            # Store in conversation history
            self.conversation_history.append(Message(role="user", content=text))
            
            # Limit context window to prevent token overflow
            max_context = self.config.get('operator', {}).get('max_context_length', 8192)
            messages_for_llm = self._get_context_messages(max_context)
            
            # Generate response using LLM (Gemini)
            response = self.llm.generate_response(
                messages=messages_for_llm,
                max_tokens=self.config.get('operator', {}).get('max_response_tokens', 500)
            )
            
            # Store response in conversation history
            self.conversation_history.append(Message(role="assistant", content=response))
            
            # Log successful processing
            self.logger.debug(f"Generated response: {response[:100]}...")
            self.current_state = "idle"
            
            return response
            
        except Exception as e:
            self.logger.error(f"Error processing input: {e}")
            self.current_state = "idle"
            return "I encountered an error processing your request. Please try again."

    def _extract_task_blocks(self, response: str):
        """Split Gemini output into spoken text and one or more task payloads."""
        task_pattern = re.compile(r'\[TASK\](.*?)\[/TASK\]', re.DOTALL)
        matches = list(task_pattern.finditer(response))
        if not matches:
            return response.strip(), []

        spoken_text = response[:matches[0].start()].strip()
        task_payloads = []

        for match in matches:
            raw_task = match.group(1).strip()
            if not raw_task:
                continue

            try:
                parsed_task = json.loads(raw_task)
            except json.JSONDecodeError as e:
                self.logger.warning("Phase 2: Invalid task JSON from Gemini: %s", e)
                continue

            if isinstance(parsed_task, list):
                for item in parsed_task:
                    if isinstance(item, dict) and item.get("protocol") == "minipupper-v1" and item.get("type") == "task":
                        task_payloads.append(item)
                continue

            if isinstance(parsed_task, dict) and parsed_task.get("protocol") == "minipupper-v1" and parsed_task.get("type") == "task":
                task_payloads.append(parsed_task)
            else:
                self.logger.warning("Phase 2: Ignoring unsupported task payload from Gemini")

        return spoken_text, task_payloads
    
    def _get_context_messages(self, max_tokens: int) -> list:
        """
        Get conversation history for LLM context.
        
        Keeps recent messages up to token limit.
        
        Args:
            max_tokens: Maximum tokens to keep in context
            
        Returns:
            List of Message objects for LLM
        """
        # For now, keep last 10 messages (can improve with actual token counting)
        max_messages = 10
        start_idx = max(0, len(self.conversation_history) - max_messages)
        
        return self.conversation_history[start_idx:]

    def _is_likely_speaker_bleed(self, transcript: str) -> bool:
        """
        Heuristic: returns True when the ASR `transcript` appears to be
        a verbatim (or nearly verbatim) echo of the last assistant message.

        Method:
        - Find the most recent assistant message in `conversation_history`.
        - Normalize both strings (lowercase, strip punctuation).
        - Compute token coverage: fraction of transcript tokens present in assistant tokens.
        - If coverage >= 0.95 and transcript has >= 3 tokens, consider it bleed.
        - Also treat as bleed when the cleaned transcript is a substring of the assistant text
          (useful for short repeats) with >=2 tokens.
        """
        if not transcript:
            return False

        # find last assistant message
        last_assistant = None
        for msg in reversed(self.conversation_history):
            if getattr(msg, 'role', None) == 'assistant' and getattr(msg, 'content', None):
                last_assistant = msg.content
                break

        if not last_assistant:
            return False

        def _clean(s: str) -> str:
            return re.sub(r"[^\w\s]", "", s.lower()).strip()

        t_clean = _clean(transcript)
        a_clean = _clean(last_assistant)

        if not t_clean:
            return False

        t_tokens = t_clean.split()
        a_tokens = set(a_clean.split())

        if not t_tokens:
            return False

        # token coverage
        matched = sum(1 for tok in t_tokens if tok in a_tokens)
        coverage = matched / float(len(t_tokens))

        if len(t_tokens) >= 3 and coverage >= 0.95:
            return True

        # substring check for shorter transcripts
        if len(t_tokens) >= 2 and t_clean in a_clean:
            return True

        return False

    def _is_interrupt_command(self, transcript: str) -> bool:
        """
        Heuristic to detect short explicit user interrupt phrases.
        Returns True for clear short commands like "stop", "cancel", "that's enough", etc.
        """
        if not transcript:
            return False

        t = re.sub(r"[^\w\s]", "", transcript.lower()).strip()
        if not t:
            return False

        # exact phrases
        phrases = {"stop", "cancel", "cancel output", "thats enough", "that's enough", "stop that", "interrupt", "abort", "never mind"}
        if t in phrases:
            return True

        tokens = t.split()
        # single-word interrupts
        if len(tokens) <= 3 and tokens and tokens[0] in {"stop", "cancel", "abort", "interrupt"}:
            return True

        return False
    
    def _execute_movement(self, command: str):
        """
        Execute movement command.
        
        Args:
            command: Movement command string
        """
        self.logger.info(f"Executing movement: {command}")
        
        # TODO: Implement actual movement commands
        # Map commands to motor control
        movements = {
            "sit": self._sit,
            "stand": self._stand,
            "forward": self._move_forward,
            "backward": self._move_backward,
            "left": self._move_left,
            "right": self._move_right,
        }
        
        if command in movements:
            movements[command]()
        else:
            self.logger.warning(f"Unknown movement: {command}")
    
    # Movement placeholders
    def _sit(self):
        """Sit down"""
        self.logger.debug("Robot sitting")
        self._broadcast_status("Sitting")
    
    def _stand(self):
        """Stand up"""
        self.logger.debug("Robot standing")
        self._broadcast_status("Standing")
    
    def _move_forward(self):
        """Move forward"""
        self.logger.debug("Moving forward")
        self._broadcast_status("Moving forward")
    
    def _move_backward(self):
        """Move backward"""
        self.logger.debug("Moving backward")
        self._broadcast_status("Moving backward")
    
    def _move_left(self):
        """Move left"""
        self.logger.debug("Moving left")
        self._broadcast_status("Moving left")
    
    def _move_right(self):
        """Move right"""
        self.logger.debug("Moving right")
        self._broadcast_status("Moving right")
    
    def _set_mute_volume(self):
        """Set PulseAudio volume based on mute_mode flag.

        In mute mode, sets speaker volume to 0% but keeps TTS pipeline running.
        When unmuted, restores to 100%.
        """
        try:
            import subprocess
            volume = "0%" if self.mute_mode else "100%"
            # Try both AEC sink and direct PulseAudio default
            subprocess.run(
                ["pactl", "set-sink-volume", "aec_sink_hp", volume],
                capture_output=True, timeout=2
            )
            subprocess.run(
                ["pactl", "set-sink-volume", "@DEFAULT_SINK@", volume],
                capture_output=True, timeout=2
            )
            self.logger.info(f"Mute volume set to {volume}")
        except Exception as e:
            self.logger.debug(f"Cannot set PulseAudio volume: {e}")

    def _broadcast_status(self, status: str):
        """Broadcast status update"""
        try:
            status_queue.put(status, timeout=0.1)
        except:
            pass  # Queue full, skip update


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Minipupper Operator — Autonomous robot assistant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  %(prog)s                          Normal mode (voice in/out)
  %(prog)s -k                       Keyboard input mode (no STT)
  %(prog)s -m                       Mute mode (no TTS, output in log)
  %(prog)s -k -m                    Keyboard + silent (dev mode)
        """
    )
    parser.add_argument(
        "-k", "--keyboard",
        action="store_true",
        help="Disable speech-to-text; use terminal keyboard for input"
    )
    parser.add_argument(
        "-m", "--mute",
        action="store_true",
        help="Disable text-to-speech; show responses on screen only"
    )
    args = parser.parse_args()

    operator = MinipupperOperator(keyboard=args.keyboard, mute=args.mute)

    try:
        operator.start()

        if args.keyboard:
            logger.info("\u2713 Minipupper Operator running. Using KEYBOARD input.")
            logger.info("Type your messages in the terminal and press Enter.")
        elif args.mute:
            logger.info("\u2713 Minipupper Operator running. TTS is MUTED.")
            logger.info("Listening for speech... (output shown in log)")
        else:
            logger.info("\u2713 Minipupper Operator running. Listening for speech...")
        logger.info("Press Ctrl+C to stop.")

        # Keep running and wait for signals
        while operator.is_running:
            time.sleep(0.5)

    except KeyboardInterrupt:
        logger.info("\nReceived shutdown signal")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        logger.info("Shutting down...")
        operator.stop()
        logger.info("Operator stopped")


if __name__ == "__main__":
    main()
