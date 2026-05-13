#!/usr/bin/env python3
"""
Mini Pupper — Camera Person Follower (FPC API)

Uses background subtraction + centroid tracking to detect and follow
a moving person. No ML libraries required — pure OpenCV computer vision.

Movement uses the FPC ContinuousController instead of the UDP joystick.

Flow:
  1. Capture frames from /dev/video0
  2. Background subtraction (MOG2) → foreground mask
  3. Find largest contour → compute centroid
  4. Map centroid position to velocities
  5. ContinuousController.set_velocity() + .tick()

Usage:
  python3 custom/camera_person_follower.py              # follow (3 min default)
  python3 custom/camera_person_follower.py --duration 60
  python3 custom/camera_person_follower.py --preview     # show CV preview
  python3 custom/camera_person_follower.py --method color
"""

import sys, os, time, argparse

sys.path.insert(0, os.path.expanduser("~/minipupper-app"))
from robot.continuous_control import ContinuousController

import cv2
import numpy as np

# ── Constants ──────────────────────────────────────────────────

CAMERA_DEVICE = 0
FRAME_WIDTH = 320
FRAME_HEIGHT = 240
MIN_CONTOUR_AREA = 500
MAX_CONTOUR_AREA = 80000

# FPC velocity limits (from ContinuousController)
VX_MAX = 0.5
VY_MAX = 0.5
YAW_MAX = 1.0


# ── Tracking Methods ───────────────────────────────────────────

def track_motion(frame, fgbg=None):
    """Background subtraction + contour detection."""
    if fgbg is None:
        fgbg = cv2.createBackgroundSubtractorMOG2(history=500, varThreshold=64)

    fgmask = fgbg.apply(frame)
    fgmask = cv2.erode(fgmask, None, iterations=1)
    fgmask = cv2.dilate(fgmask, None, iterations=2)

    contours, _ = cv2.findContours(fgmask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None, fgbg

    largest = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(largest)
    if area < MIN_CONTOUR_AREA or area > MAX_CONTOUR_AREA:
        return None, fgbg

    x, y, w, h = cv2.boundingRect(largest)
    h_frame, w_frame = frame.shape[:2]
    return (x + w // 2, y + h // 2, area, w_frame, h_frame), fgbg


def track_color(frame, lower_hsv=None, upper_hsv=None):
    """HSV color tracking (default: warm/skin tones)."""
    if lower_hsv is None:
        lower_hsv = np.array([0, 30, 50])
        upper_hsv = np.array([25, 255, 255])

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
    h_frame, w_frame = frame.shape[:2]
    return (x + w // 2, y + h // 2, area, w_frame, h_frame)


# ── Main Follower Loop ─────────────────────────────────────────

def follow(method="motion", duration=180, preview=False):
    """Run person following loop.

    Args:
        method: "motion" (MOG2) or "color" (HSV)
        duration: Seconds to run
        preview: Show OpenCV preview window
    """
    cap = cv2.VideoCapture(CAMERA_DEVICE)
    if not cap.isOpened():
        print("ERROR: Could not open camera")
        return False

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

    time.sleep(0.5)
    for _ in range(5):
        cap.read()

    print(f"  Camera ready ({FRAME_WIDTH}x{FRAME_HEIGHT})")

    # Use FPC ContinuousController
    ctrl = ContinuousController()
    print("  Activating robot...")
    ctrl.activate()
    print("  Following started. Press Ctrl+C to stop.")

    fgbg = None
    start_time = time.time()
    last_seen_time = time.time()
    target_lost = False
    frame_count = 0

    try:
        while time.time() - start_time < duration:
            ret, frame = cap.read()
            if not ret:
                continue

            frame_count += 1

            # Track at camera fps
            if method == "color":
                result = track_color(frame)
            else:
                result, fgbg = track_motion(frame, fgbg)

            if preview and result:
                cx, cy, area, _, _ = result
                cv2.circle(frame, (cx, cy), 8, (0, 255, 0), -1)
                cv2.rectangle(frame,
                    (cx - int(area**0.5)//2, cy - int(area**0.5)//2),
                    (cx + int(area**0.5)//2, cy + int(area**0.5)//2),
                    (0, 255, 0), 2)

            if result is not None:
                cx, cy, area, w_frame, h_frame = result
                target_lost = False
                last_seen_time = time.time()

                # Normalized errors
                error_x = (cx - w_frame // 2) / (w_frame // 2)
                area_ratio = area / (w_frame * h_frame)

                # Yaw: rotate to center target (dead zone 15%)
                yaw = max(-YAW_MAX, min(YAW_MAX, error_x * 0.8)) if abs(error_x) > 0.15 else 0.0

                # Forward: maintain distance based on blob size
                if area_ratio < 0.05:
                    vx = 0.3  # too far
                elif area_ratio > 0.25:
                    vx = -0.2  # too close
                else:
                    vx = 0.0  # good distance

                ctrl.set_velocity(vx=vx, vy=0)
                ctrl.set_yaw_rate(rate=yaw)

                if preview:
                    cv2.putText(frame,
                        f"vx={vx:.2f} yaw={yaw:.2f}",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

            else:
                ctrl.stop()
                if not target_lost:
                    target_lost = True
                    print("  Target lost, waiting...")
                if preview:
                    cv2.putText(frame, "NO TARGET", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
                if time.time() - last_seen_time > 10:
                    print(f"  Target lost for 10s, stopping.")
                    break

            # Send commands to servos every frame
            ctrl.tick()

            if preview:
                cv2.imshow("Person Follower", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

    except KeyboardInterrupt:
        print("  Stopped by user")

    finally:
        ctrl.stop()
        print("  Deactivating...")
        ctrl.deactivate()
        cap.release()
        if preview:
            cv2.destroyAllWindows()

    elapsed = time.time() - start_time
    print(f"  Ran for {elapsed:.0f}s")
    return True


def main():
    parser = argparse.ArgumentParser(description="Mini Pupper Person Follower")
    parser.add_argument("--duration", type=int, default=180)
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--method", choices=["motion", "color"], default="motion")
    parser.add_argument("--test", action="store_true", help="Camera test only")
    args = parser.parse_args()

    if args.test:
        cap = cv2.VideoCapture(CAMERA_DEVICE)
        if not cap.isOpened():
            print("FAIL: Camera not accessible")
            return 1
        ret, frame = cap.read()
        if ret:
            print(f"OK: Camera captures at {frame.shape[1]}x{frame.shape[0]}")
            cv2.imwrite("/tmp/follower_test.jpg", frame)
            print("OK: Test image saved")
        else:
            print("FAIL: Could not read frame")
            return 1
        cap.release()
        return 0

    print("Camera Person Follower (FPC API)")
    print(f"  Method: {args.method}")
    print(f"  Duration: {args.duration}s")
    success = follow(method=args.method, duration=args.duration, preview=args.preview)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
