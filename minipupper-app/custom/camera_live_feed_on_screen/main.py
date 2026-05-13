#!/usr/bin/env python3
"""
Mini Pupper - Live Camera Feed on ST7789 LCD

Captures a continuous live video stream from the MIPI CSI camera
(/dev/video0) and displays it on the onboard ST7789 LCD (320x240).

Features:
- Continuous live feed at ~10-15 FPS
- Graceful shutdown on Ctrl+C, 'q' key, or timeout
- Optional duration limit
- Low-latency single-threaded loop (SPI is the bottleneck, not CPU)
- Signal-safe cleanup

Usage:
  python main.py                    # run indefinitely until Ctrl+C or 'q'
  python main.py --duration 30      # run for 30 seconds then stop
  python main.py --test             # quick 5-second test
  python main.py --record /tmp/feed.mp4  # record while displaying
"""

import argparse
import signal
import sys
import time

import cv2
import numpy as np
from PIL import Image


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
CAMERA_DEVICE = 0          # /dev/video0
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
DISPLAY_WIDTH = 320
DISPLAY_HEIGHT = 240
DISPLAY_BPP = ST7789 = None  # imported lazily


# ---------------------------------------------------------------------------
# Signal / quit handling
# ---------------------------------------------------------------------------
_running = True

def _signal_handler(sig, frame):
    global _running
    _running = False

signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


def _check_quit_key():
    """Return True if 'q' has been pressed on OpenCV window.
    Also respects global _running flag."""
    global _running
    if not _running:
        return True
    try:
        return cv2.waitKey(1) & 0xFF == ord('q')
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------
def open_camera():
    """Open the MIPI CSI camera and configure for 640x480."""
    cap = cv2.VideoCapture(CAMERA_DEVICE)
    if not cap.isOpened():
        print("ERROR: Could not open camera /dev/video0", file=sys.stderr)
        return None
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
    # Let camera warm up
    for _ in range(5):
        cap.read()
    return cap


def capture_frame(cap):
    """Capture a single frame. Returns BGR numpy array or None."""
    ret, frame = cap.read()
    if not ret or frame is None:
        return None
    return frame


def frame_to_display_image(frame_bgr):
    """Convert BGR OpenCV frame → resized RGB PIL Image for display."""
    frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(frame_rgb)
    return pil_img.resize((DISPLAY_WIDTH, DISPLAY_HEIGHT))


# ---------------------------------------------------------------------------
# Display (ST7789 LCD on Mini Pupper)
# ---------------------------------------------------------------------------
def get_display():
    """Initialize and return the Display object. Returns None on failure."""
    try:
        from MangDang.mini_pupper.display import Display
        return Display()
    except ImportError:
        print("ERROR: MangDang.mini_pupper.display not available", file=sys.stderr)
        return None
    except Exception as e:
        print(f"ERROR: Display init failed: {e}", file=sys.stderr)
        return None


def show_frame(disp, pil_img):
    """Push a PIL Image to the LCD display."""
    try:
        disp.disp.display(pil_img)
        return True
    except Exception as e:
        print(f"WARN: Display write failed: {e}", file=sys.stderr)
        return False


# ---------------------------------------------------------------------------
# Optional video recording
# ---------------------------------------------------------------------------
def setup_recorder(output_path, fps=15.0):
    """Set up an MP4 video writer (XVID codec, 320x240)."""
    fourcc = cv2.VideoWriter_fourcc(*'XVID')
    writer = cv2.VideoWriter(output_path, fourcc, fps, (DISPLAY_WIDTH, DISPLAY_HEIGHT))
    if not writer.isOpened():
        print(f"WARN: Could not open video writer for {output_path}", file=sys.stderr)
        return None
    return writer


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def run_live_feed(duration=None, record_path=None):
    """
    Main live-feed loop.

    Parameters
    ----------
    duration : float or None
        Run for this many seconds, then stop. None = run until user quits.
    record_path : str or None
        If set, record video to this file.
    """
    global _running
    _running = True

    # -- Init camera --
    cap = open_camera()
    if cap is None:
        return 1

    # -- Init display --
    disp = get_display()
    if disp is None:
        cap.release()
        return 1

    # -- Init recorder (optional) --
    writer = None
    if record_path:
        writer = setup_recorder(record_path)
        if writer is None:
            print("Continuing without recording...")

    # -- Timing --
    start_time = time.time()
    frame_count = 0
    fps_report_interval = 5.0  # report FPS every 5 seconds
    last_fps_report = start_time

    print("Live camera feed started. Press Ctrl+C or 'q' (on OpenCV window) to stop.")
    if duration:
        print(f"Auto-stopping after {duration:.0f} seconds.")

    try:
        while _running:
            # Check duration limit
            elapsed = time.time() - start_time
            if duration and elapsed >= duration:
                print(f"Duration limit reached ({duration:.0f}s). Stopping.")
                break

            # Capture
            frame = capture_frame(cap)
            if frame is None:
                print("WARN: Frame capture failed, retrying...", file=sys.stderr)
                time.sleep(0.05)
                continue

            # Convert and display
            display_img = frame_to_display_image(frame)
            show_frame(disp, display_img)

            # Record if desired
            if writer is not None:
                resized_rgb = cv2.resize(
                    frame, (DISPLAY_WIDTH, DISPLAY_HEIGHT)
                )
                writer.write(
                    cv2.cvtColor(resized_rgb, cv2.COLOR_RGB2BGR)
                )

            frame_count += 1

            # Periodic FPS report
            if time.time() - last_fps_report >= fps_report_interval:
                actual_fps = frame_count / (time.time() - last_fps_report)
                print(f"  Feed running: ~{actual_fps:.1f} FPS, {frame_count} frames shown")
                last_fps_report = time.time()
                frame_count = 0

            # Quick check for keyboard 'q'
            if _check_quit_key():
                print("'q' pressed. Stopping.")
                break

    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    except Exception as e:
        print(f"ERROR in feed loop: {e}", file=sys.stderr)
    finally:
        # Cleanup
        cap.release()
        if writer is not None:
            writer.release()
        # Show a blank screen on exit
        try:
            blank = Image.new("RGB", (DISPLAY_WIDTH, DISPLAY_HEIGHT), (0, 0, 0))
            show_frame(disp, blank)
        except Exception:
            pass
        print("Live feed stopped. Screen cleared.")

    return 0


def test_feed_quick():
    """
    Quick self-test: run for 5 seconds and verify basic pipeline works.
    """
    print("=== Live Feed Self-Test (5 seconds) ===")

    # 1. Camera check
    cap = open_camera()
    if cap is None:
        print("FAIL: Camera not available")
        return 1
    frame = capture_frame(cap)
    cap.release()
    if frame is None:
        print("FAIL: Cannot capture frame")
        return 1
    print(f"  Camera: OK ({frame.shape[1]}x{frame.shape[0]})")

    # 2. Display check (import + resize)
    disp = get_display()
    if disp is None:
        print("FAIL: Display not available (non-fatal if testing headless)")
    else:
        print("  Display: OK (module loaded)")

    # 3. Resize + color convert
    display_img = frame_to_display_image(frame)
    assert display_img.size == (DISPLAY_WIDTH, DISPLAY_HEIGHT), \
        f"Resize mismatch: {display_img.size} != ({DISPLAY_WIDTH},{DISPLAY_HEIGHT})"
    print(f"  Image pipeline: OK ({display_img.size[0]}x{display_img.size[1]})")

    # 4. Full 5s run
    print("  Running 5-second feed...")
    ret = run_live_feed(duration=5.0)
    if ret != 0:
        print(f"FAIL: run_live_feed returned {ret}")
        return 1
    print("  5-second feed: OK")

    print("=== Self-test PASSED ===")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Mini Pupper - Live Camera Feed on ST7789 LCD"
    )
    parser.add_argument('--duration', type=float, default=None,
                        help='Run for N seconds then stop (default: unlimited)')
    parser.add_argument('--record', type=str, default=None,
                        help='Record video to file (e.g. /tmp/feed.mp4)')
    parser.add_argument('--test', action='store_true',
                        help='Run quick 5-second self-test')
    args = parser.parse_args()

    if args.test:
        return test_feed_quick()

    return run_live_feed(duration=args.duration, record_path=args.record)


if __name__ == "__main__":
    sys.exit(main())
