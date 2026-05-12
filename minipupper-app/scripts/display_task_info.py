#!/usr/bin/env python3
"""
Display task information on the Mini Pupper ST7789 LCD screen.

Draws current task status as text on the 320x240 display.
Supports showing action name, status, phase, and progress.
"""

import os
import time
from PIL import Image, ImageDraw, ImageFont
from enum import Enum


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    IDLE = "idle"


# Color scheme
BG_IDLE = (10, 10, 30)          # Dark navy when idle
BG_PENDING = (30, 20, 10)       # Dark amber when task queued
BG_RUNNING = (10, 30, 10)       # Dark green when processing
BG_COMPLETED = (10, 40, 10)     # Brighter green when done
BG_FAILED = (40, 10, 10)        # Dark red on failure

TEXT_WHITE = (220, 220, 220)
TEXT_GREEN = (100, 220, 100)
TEXT_AMBER = (220, 180, 60)
TEXT_RED = (220, 80, 80)
TEXT_DIM = (120, 120, 130)

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _get_font(size: int):
    """Load the DejaVu font at the requested size."""
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except (IOError, OSError):
        return ImageFont.load_default()


def make_display_image(
    action: str = "",
    status: str = "idle",
    phase: str = "",
    progress: float = 0,
    message: str = "",
    current_time: str = "",
):
    """Render a 320x240 image showing current task state.

    Args:
        action: Task action name (e.g. "web_search", "robot.move_forward")
        status: One of "idle", "pending", "running", "completed", "failed"
        phase: Current phase text
        progress: Progress percentage (0-100)
        message: Status message
        current_time: Optional time string to show

    Returns:
        PIL Image ready for display
    """
    # Pick background and text colors based on status
    st = status.lower()
    if st == "pending":
        bg = BG_PENDING
        status_color = TEXT_AMBER
        status_label = "QUEUED"
    elif st == "running":
        bg = BG_RUNNING
        status_color = TEXT_GREEN
        status_label = "RUNNING"
    elif st == "completed":
        bg = BG_COMPLETED
        status_color = TEXT_GREEN
        status_label = "DONE"
    elif st == "failed":
        bg = BG_FAILED
        status_color = TEXT_RED
        status_label = "FAILED"
    else:
        bg = BG_IDLE
        status_color = TEXT_DIM
        status_label = "LISTENING"

    img = Image.new("RGB", (320, 240), color=bg)
    draw = ImageDraw.Draw(img)

    font_large = _get_font(28)
    font_medium = _get_font(18)
    font_small = _get_font(14)

    y = 10

    # Status bar at top
    if st != "idle":
        # Action name
        action_label = action.replace("robot.", "").replace("_", " ").upper()
        if len(action_label) > 25:
            action_label = action_label[:22] + "..."

        draw.text((12, y), action_label, font=font_medium, fill=TEXT_WHITE)
        y += 30

        # Status chip
        draw.text((12, y), status_label, font=font_large, fill=status_color)

        # Progress bar (if running or completed)
        if progress > 0:
            bar_x = 12
            bar_y = y + 35
            bar_w = 296
            bar_h = 12
            fill_w = int(bar_w * min(progress / 100.0, 1.0))

            # Background
            draw.rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h],
                           fill=(40, 40, 50))
            # Fill
            if fill_w > 0:
                fill_color = TEXT_GREEN if st == "completed" else TEXT_AMBER
                draw.rectangle([bar_x, bar_y, bar_x + fill_w, bar_y + bar_h],
                               fill=fill_color)

            draw.text((bar_x + bar_w + 8, bar_y - 2),
                      f"{int(progress)}%", font=font_small, fill=TEXT_DIM)
            y = bar_y + bar_h + 8
        else:
            y += 40

        # Task message
        if message and len(message) > 3:
            # Word-wrap message
            words = message.split()
            lines = []
            current_line = ""
            for word in words:
                test_line = f"{current_line} {word}".strip()
                if len(test_line) * 9 > 290:  # Rough estimate
                    lines.append(current_line)
                    current_line = word
                else:
                    current_line = test_line
            lines.append(current_line)

            for line in lines[:3]:  # Max 3 lines
                draw.text((12, y), line, font=font_small, fill=TEXT_DIM)
                y += 20
    else:
        # Idle state - show pulsing "LISTENING..."
        draw.text((12, y), "MINIPUPPER", font=font_large, fill=status_color)
        y += 40
        draw.text((12, y), "Listening for speech...", font=font_medium, fill=TEXT_DIM)

    # Clock/time at bottom
    if current_time:
        draw.text((12, 220), current_time, font=font_small, fill=TEXT_DIM)

    return img


class TaskDisplay:
    """Manages the LCD display for task status updates."""

    _instance = None

    def __init__(self):
        self._disp = None
        self._last_hash = None
        self._init_display()

    def _init_display(self):
        try:
            from MangDang.mini_pupper.display import Display
            self._disp = Display()
        except ImportError:
            self._disp = None

    @property
    def available(self) -> bool:
        return self._disp is not None

    def show_task(self, action="", status="idle", phase="", progress=0,
                  message="", time_str=""):
        """Render and display current task state on the LCD.

        Only updates the physical display when the content actually changes
        (to avoid flicker).
        """
        if not self._disp:
            return

        # Compute a quick hash to detect meaningful changes
        content = f"{action}|{status}|{phase}|{progress}|{message}"
        h = hash(content)
        if h == self._last_hash:
            return
        self._last_hash = h

        try:
            img = make_display_image(
                action=action,
                status=status,
                phase=phase,
                progress=progress,
                message=message,
                current_time=time_str or time.strftime("%H:%M"),
            )
            self._disp.disp.display(img)
        except Exception:
            pass  # Don't crash the app if display fails

    def show_idle(self):
        """Show the idle listening state."""
        self.show_task(status="idle")


def main():
    """Quick test — cycle through task states on the display."""
    disp = TaskDisplay()
    print(f"Display available: {disp.available}")

    states = [
        ("web_search", "pending", "queued", 0, "Searching for weather..."),
        ("web_search", "running", "processing", 30, "Fetching results..."),
        ("web_search", "running", "processing", 70, "Almost there..."),
        ("web_search", "completed", "done", 100, "Found: 28°C, cloudy"),
        ("robot.take_photo_and_show", "running", "capturing", 50, "Smile! 📸"),
        ("robot.take_photo_and_show", "completed", "done", 100, "Photo displayed!"),
    ]

    for action, status, phase, progress, msg in states:
        print(f"Showing: [{status}] {action}")
        disp.show_task(action=action, status=status, phase=phase,
                       progress=progress, message=msg)
        time.sleep(2)

    disp.show_idle()


if __name__ == "__main__":
    main()
