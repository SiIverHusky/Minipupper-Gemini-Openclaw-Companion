"""
Minipupper Operator - Main Application
Autonomous Operator role with robust capabilities
Last Updated: 2026-05-09
"""

import logging
import os
import sys
import yaml
import threading
from pathlib import Path
from typing import Dict, Any

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

from src.core.task_queue import (
    input_text_queue, output_text_queue, barge_in_detected,
    speech_active, movement_queue, status_queue, control_queue
)
from src.audio.audio_manager import AudioManager, AudioConfig
from src.audio.barge_in_detector import BargeInConfig
from src.core.llm_engine import create_llm_provider, Message

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
    
    def __init__(self, config_path: str = "config/config.yaml"):
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
            asr_engine=os.getenv('ASR_ENGINE', asr_settings.get('engine', 'google')),
            asr_model=os.getenv('WHISPER_MODEL', asr_settings.get('model', 'base')),
            asr_device=os.getenv('WHISPER_DEVICE', asr_settings.get('device', 'cpu')),
            tts_engine=tts_settings.get('engine', 'google'),
            language_code=asr_settings.get('language', 'en-US'),
        )
        self.audio_manager = AudioManager(audio_config)
        
        # LLM Engine (Gemini via Vertex AI)
        self.llm = create_llm_provider(
            provider_name=self.config.get('operator', {}).get('llm_provider', 'gemini'),
            project_id=os.getenv('GOOGLE_CLOUD_PROJECT_ID'),
            model=self.config.get('operator', {}).get('llm_model', 'gemini-1.5-flash'),
        )
        
        # State
        self.is_running = False
        self.current_state = "idle"
        self.conversation_history = []
        
        # Thread pool
        self._worker_threads = []
        self._stop_event = threading.Event()
        
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
        self.logger.info("Minipupper Operator stopped")
    
    def _start_workers(self):
        """Start background worker threads"""
        # ASR Worker - converts speech to text
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
    
    def _asr_worker(self):
        """Worker: Speech-to-text processing"""
        self.logger.info("ASR Worker started")
        
        while self.is_running:
            try:
                # TODO: Implement continuous audio capture
                # For now, wait for manual input
                pass
            except Exception as e:
                self.logger.error(f"ASR Worker error: {e}")
    
    def _operator_worker(self):
        """Worker: Process input and generate responses"""
        self.logger.info("Operator Worker started")
        
        while self.is_running:
            try:
                # Check for input text
                try:
                    text = input_text_queue.get(timeout=1.0)
                except:
                    continue
                
                # Process and respond
                response = self._process_user_input(text)
                
                if response:
                    output_text_queue.put(response)
                    
                    # Speak response with barge-in support
                    if self.config['audio']['tts']['engine'] == 'google':
                        interrupted = not self.audio_manager.speak(response)
                        if interrupted:
                            self._broadcast_status("Speech interrupted by user")
                    
            except Exception as e:
                self.logger.error(f"Operator Worker error: {e}")
    
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
    
    def _broadcast_status(self, status: str):
        """Broadcast status update"""
        try:
            status_queue.put(status, timeout=0.1)
        except:
            pass  # Queue full, skip update


def main():
    """Main entry point"""
    operator = MinipupperOperator()
    
    try:
        operator.start()
        
        # Keep running
        import time
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    finally:
        operator.stop()


if __name__ == "__main__":
    main()
