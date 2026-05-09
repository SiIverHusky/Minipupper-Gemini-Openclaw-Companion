"""
Minipupper Operator - Task Queue
Thread-safe queues for inter-component communication
Last Updated: 2026-05-09
"""

import queue
import threading
from typing import Any

# Speech-to-Text: ASR engine → Input text queue
input_text_queue = queue.Queue()

# Text-to-Speech: Output text queue → TTS engine
output_text_queue = queue.Queue()

# Barge-in Detection: Audio stream → Barge-in trigger
barge_in_detected = queue.Queue()

# Speech Activity: Tracks when TTS is active (for ASR muting)
# Put True when speaking starts, False when speaking ends
speech_active = queue.Queue()

# GIF/Animation queue: True to show, False to hide
gif_queue = queue.Queue()

# Image display queue: PIL Image objects
image_queue = queue.Queue()

# Movement commands queue: Movement text ("sit", "forward", etc)
movement_queue = queue.Queue()

# Status updates: Human-readable status strings
status_queue = queue.Queue()

# Control commands: System control (shutdown, restart, etc)
control_queue = queue.Queue()


def put_async(q: queue.Queue, item: Any, timeout: float = 1.0) -> bool:
    """
    Non-blocking queue put with timeout.
    
    Args:
        q: Queue to put item into
        item: Item to queue
        timeout: Timeout in seconds
        
    Returns:
        True if successful, False if queue was full
    """
    try:
        q.put(item, timeout=timeout)
        return True
    except queue.Full:
        return False


def get_latest(q: queue.Queue, default: Any = None) -> Any:
    """
    Get the latest item from queue, discarding older items.
    Useful for sensor/status updates where we only care about current state.
    
    Args:
        q: Queue to drain
        default: Default value if queue is empty
        
    Returns:
        Latest item or default
    """
    item = default
    try:
        while True:
            item = q.get_nowait()
    except queue.Empty:
        pass
    return item
