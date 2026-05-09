"""
Minipupper Operator Application
Main entry point and initialization
"""

__version__ = "0.1.0-alpha"
__author__ = "Minipupper Team"
__description__ = "Voice-first AI Assistant for Minipupper robot with barge-in support"

from src.core.task_queue import (
    input_text_queue,
    output_text_queue,
    barge_in_detected,
    speech_active,
    movement_queue,
    status_queue,
    control_queue,
)

__all__ = [
    "input_text_queue",
    "output_text_queue",
    "barge_in_detected",
    "speech_active",
    "movement_queue",
    "status_queue",
    "control_queue",
]
