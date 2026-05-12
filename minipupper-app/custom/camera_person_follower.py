#!/usr/bin/env python3
"""
Mini Pupper — Camera Person Follower

Uses background subtraction + centroid tracking to detect and follow
a moving person. No ML libraries required — pure OpenCV computer vision.

Flow:
  1. Capture frames from /dev/video0
  2. Background subtraction (MOG2) → foreground mask
  3. Find largest contour → compute centroid
  4. Map centroid position to robot movement commands
  5. Send UDP joystick messages to the robot controller

Usage:
  python3 custom/camera_person_follower.py          # follow (3 min default)
  python3 custom/camera_person_follower.py --duration 60  # follow for 60s
  python3 custom/camera_person_follower.py --preview     # show CV preview
  python3 custom/camera_person_follower.py --method color  # color tracking
"""

import sys, os, time, argparse, math

sys.path.insert(0, os.path.expanduser("~/apps-md-robots"))
from api.UDPComms import Publisher

import cv2
import numpy as np

# ── Constants ──────────────────────────────────────────────────

CAMERA_DEVICE = 0
FRAME_WIDTH = 320   # half res for speed
FRAME_HEIGHT = 240
FOLLOW_INTERVAL = 0.1  # 10 Hz control loop
MIN_CONTOUR_AREA = 500  # minimum blob size to track
MAX_CONTOUR_AREA = 80000  # max blob size

# UDP joystick protocol
pub = Publisher(8830, "127.0.0.1")
MSG = {"L1": False, "R1": False, "L2": -1.0, "R2": -1.0,
       "x": False, "square": False, "circle": False, "triangle": False,
       "lx": 0.0, "ly": 0.0, "rx": 0.0, "ry": 0.0,
       "dpadx": 0, "dpady": 0, "message_rate": 20}


def _rising_edge(button, hold=0.05, gap=0.15):
    pub.send({**MSG, button: True})
    time.sleep(hold)
    pub.send({**MSG, button: False})
    time.sleep(gap)


def _hold_cmd(field, value, duration):
    n = int(duration / FOLLOW_INTERVAL)
    for _ in range(n):
        pub.send({**MSG, field: value})
        time.sleep(FOLLOW_INTERVAL)
    pub.send({**MSG, field: 0.0})
    time.sleep(0.05)


def activate_robot():
    """Activate and raise body to standing position."""
    print("  Activating robot...")
    _rising_edge("L1")
    time.sleep(0.15)
    _hold_cmd("dpady", 0.5, 0.5)


def trot_toggle():
    _rising_edge("R1")


def stop_robot():
    pub.send({**MSG, "lx": 0.0, "ly": 0.0, "rx": 0.0, "ry": 0.0})


def deactivate_robot():
    _rising_edge("L1")


# ── Tracking Methods ───────────────────────────────────────────

def track_motion(frame, fgbg=None):
    """Background subtraction + contour detection.
    
    Returns: (center_x, center_y, area, frame_width, frame_height) or None
    """
    if fgbg is None:
        fgbg = cv2.createBackgroundSubtractorMOG2(history=500, varThreshold=64)
    
    fgmask = fgbg.apply(frame)
    # Clean up noise
    fgmask = cv2.erode(fgmask, None, iterations=1)
    fgmask = cv2.dilate(fgmask, None, iterations=2)
    
    contours, _ = cv2.findContours(fgmask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if not contours:
        return None, fgbg
    
    # Find largest contour
    largest = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(largest)
    
    if area < MIN_CONTOUR_AREA or area > MAX_CONTOUR_AREA:
        return None, fgbg
    
    x, y, w, h = cv2.boundingRect(largest)
    center_x = x + w // 2
    center_y = y + h // 2
    h, w_frame = frame.shape[:2]
    
    return (center_x, center_y, area, w_frame, h), fgbg


def track_color(frame, lower_hsv=None, upper_hsv=None):
    """HSV color-based tracking. Default: warm/red tones (skin)."""
    if lower_hsv is None:
        lower_hsv = np.array([0, 30, 50])   # broad warm range
        upper_hsv = np.array([25, 255, 255]) # skin tones
    
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, lower_hsv, upper_hsv)
    mask = cv2.erode(mask, None, iterations=1)
    mask = cv2.dilate(mask, None, iterations=2)
    
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if not contours:
        return None
    
    largest = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(largest)
    
    if area < MIN_CONTOUR_AREA:
        return None
    
    x, y, w, h = cv2.boundingRect(largest)
    center_x = x + w // 2
    center_y = y + h // 2
    h_frame, w_frame = frame.shape[:2]
    
    return (center_x, center_y, area, w_frame, h_frame)


# ── Main Follower Loop ─────────────────────────────────────────

def follow(method="motion", duration=180, preview=False):
    """
    Main follow loop.
    
    Args:
        method: "motion" (MOG2) or "color" (HSV)
        duration: seconds to run
        preview: show OpenCV preview window
    """
    cap = cv2.VideoCapture(CAMERA_DEVICE)
    if not cap.isOpened():
        print("ERROR: Could not open camera")
        return False
    
    # Set lower resolution for speed
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
    
    # Warm up camera
    time.sleep(0.5)
    for _ in range(5):
        cap.read()
    
    print(f"  Camera ready ({FRAME_WIDTH}x{FRAME_HEIGHT})")
    print("  Activating robot...")
    activate_robot()
    time.sleep(0.3)
    trot_toggle()
    time.sleep(0.2)
    print("  Following started. Press Ctrl+C to stop.")
    
    fgbg = None
    start_time = time.time()
    last_seen_time = time.time()
    target_lost = False
    
    try:
        while time.time() - start_time < duration:
            ret, frame = cap.read()
            if not ret:
                continue
            
            # Track
            if method == "color":
                result = track_color(frame)
            else:
                result, fgbg = track_motion(frame, fgbg)
            
            h_frame, w_frame = frame.shape[:2]
            frame_center_x = w_frame // 2
            frame_center_y = h_frame // 2
            center_zone = w_frame * 0.2  # 20% dead zone in center
            
            if preview and result:
                # Draw tracking visualization
                cx, cy, area, _, _ = result
                cv2.circle(frame, (cx, cy), 8, (0, 255, 0), -1)
                cv2.rectangle(frame, 
                    (cx - int(area**0.5)//2, cy - int(area**0.5)//2),
                    (cx + int(area**0.5)//2, cy + int(area**0.5)//2),
                    (0, 255, 0), 2)
            
            if result is not None:
                cx, cy, area, _, _ = result
                target_lost = False
                last_seen_time = time.time()
                
                # Compute error signals (normalized -1 to 1)
                error_x = (cx - frame_center_x) / frame_center_x
                error_y = (cy - frame_center_y) / frame_center_y
                area_ratio = area / (w_frame * h_frame)
                
                # Yaw: rotate to center person horizontally (dead zone)
                if abs(error_x) > 0.15:
                    yaw = max(-0.5, min(0.5, error_x * 0.6))
                else:
                    yaw = 0.0
                
                # Forward: move based on size (closer = bigger)
                if area_ratio < 0.05:
                    forward = 0.4  # too far, move closer
                elif area_ratio > 0.25:
                    forward = -0.3  # too close, back up
                else:
                    forward = 0.0  # good distance
                
                pub.send({**MSG, "rx": yaw, "ly": forward})
                
                if preview:
                    status = f"Target: cx={cx} cy={cy} area={area:.0f} yaw={yaw:.2f} fwd={forward:.2f}"
                    cv2.putText(frame, status, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
                    cv2.line(frame, (frame_center_x, 0), (frame_center_x, h_frame), (100, 100, 100), 1)
                    cv2.rectangle(frame, 
                        (int(frame_center_x - center_zone), 0),
                        (int(frame_center_x + center_zone), h_frame),
                        (100, 100, 100), 1)
                
            else:
                # Lost target - stop
                pub.send({**MSG, "rx": 0.0, "ly": 0.0})
                
                if not target_lost:
                    target_lost = True
                    print("  Target lost, waiting...")
                
                if preview:
                    cv2.putText(frame, "NO TARGET", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
                
                # Give up after 10s of lost target
                if time.time() - last_seen_time > 10:
                    print(f"  Target lost for 10s, stopping.")
                    break
            
            if preview:
                cv2.imshow("Person Follower", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
            
            time.sleep(FOLLOW_INTERVAL)
    
    except KeyboardInterrupt:
        print("  Stopped by user")
    
    finally:
        stop_robot()
        time.sleep(0.2)
        # Don't deactivate - leave robot standing
        cap.release()
        if preview:
            cv2.destroyAllWindows()
    
    elapsed = time.time() - start_time
    print(f"  Ran for {elapsed:.0f}s")
    print("  Robot stopped. Person follower complete.")
    return True


def main():
    parser = argparse.ArgumentParser(description="Mini Pupper Person Follower")
    parser.add_argument("--duration", type=int, default=180,
                        help="Follow duration in seconds (default: 180)")
    parser.add_argument("--preview", action="store_true",
                        help="Show OpenCV preview window")
    parser.add_argument("--method", choices=["motion", "color"], default="motion",
                        help="Tracking method: motion (MOG2) or color (HSV)")
    parser.add_argument("--test", action="store_true",
                        help="Run camera test only (no robot movement)")
    args = parser.parse_args()
    
    if args.test:
        print("Testing camera only...")
        cap = cv2.VideoCapture(CAMERA_DEVICE)
        if not cap.isOpened():
            print("FAIL: Camera not accessible")
            return 1
        ret, frame = cap.read()
        if ret:
            print(f"OK: Camera captures at {frame.shape[1]}x{frame.shape[0]}")
            cv2.imwrite("/tmp/follower_test.jpg", frame)
            print("OK: Test image saved to /tmp/follower_test.jpg")
        else:
            print("FAIL: Could not read frame")
            return 1
        cap.release()
        print(f"\nTracking methods available:")
        print(f"  motion: background subtraction (MOG2)")
        print(f"  color: HSV color tracking")
        print(f"\nFull follow: python3 custom/camera_person_follower.py --duration 60 --preview")
        return 0
    
    print("Camera Person Follower starting...")
    print(f"  Method: {args.method}")
    print(f"  Duration: {args.duration}s")
    print(f"  Preview: {'yes' if args.preview else 'no'}")
    
    success = follow(method=args.method, duration=args.duration, preview=args.preview)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
