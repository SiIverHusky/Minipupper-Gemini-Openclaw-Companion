#!/usr/bin/env python3
"""
Minipupper Camera & Display Script

Captures a photo from the MIPI camera and optionally:
  - Displays it on the ST7789 LCD screen
  - Saves it to a file

Usage:
  python capture_and_show.py                        # capture + display
  python capture_and_show.py --save /tmp/photo.jpg  # capture + display + save
  python capture_and_show.py --display-only /tmp/photo.jpg  # display existing image
"""

import argparse
import os
import sys
import time
import cv2
import numpy as np
from PIL import Image


def capture_photo(output_path=None):
    """Capture a photo from the MIPI camera at /dev/video0.
    
    Returns:
        PIL Image object (RGB), or None on failure
    """
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("ERROR: Could not open camera /dev/video0", file=sys.stderr)
        return None
    
    # Warm up and capture
    time.sleep(0.5)
    ret, frame = cap.read()
    cap.release()
    
    if not ret or frame is None:
        print("ERROR: Failed to capture frame", file=sys.stderr)
        return None
    
    # Convert BGR (OpenCV) to RGB (PIL)
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(frame_rgb)
    
    if output_path:
        pil_img.save(output_path)
        print(f"Photo saved to {output_path}")
    
    return pil_img


def show_on_display(image):
    """Display a PIL Image on the ST7789 LCD screen.
    
    Auto-resizes to 320x240 to match the display.
    """
    try:
        from MangDang.mini_pupper.display import Display
        disp = Display()
        # Resize to display resolution
        display_img = image.resize((320, 240))
        disp.disp.display(display_img)
        return True
    except ImportError as e:
        print(f"ERROR: Display module not available: {e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"ERROR: Display failed: {e}", file=sys.stderr)
        return False


def display_existing_image(image_path):
    """Display an existing image file on the ST7789 LCD."""
    try:
        image = Image.open(image_path)
        return show_on_display(image)
    except Exception as e:
        print(f"ERROR: Could not open image {image_path}: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="Mini Pupper Camera & Display")
    parser.add_argument('--save', type=str, default=None,
                        help='Save photo to file path')
    parser.add_argument('--display-only', type=str, default=None,
                        help='Display an existing image file instead of capturing')
    args = parser.parse_args()
    
    if args.display_only:
        # Display existing image
        success = display_existing_image(args.display_only)
        if success:
            print("Image displayed on screen")
            return 0
        else:
            print("Failed to display image", file=sys.stderr)
            return 1
    
    # Capture and display
    pil_img = capture_photo(args.save)
    if pil_img is None:
        print("Failed to capture photo", file=sys.stderr)
        return 1
    
    success = show_on_display(pil_img)
    if success:
        print("Photo captured and displayed on screen")
    else:
        print("Photo captured but display failed", file=sys.stderr)
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
