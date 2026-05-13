#!/usr/bin/env python3
"""
Camera-based Person Following Module for Mini Pupper

Uses OpenCV HOG people detector to locate a person in the camera frame
and drives the robot to follow them via UDP joystick commands.

Usage:
    python3 custom/camera_person_follow/main.py
    python3 custom/camera_person_follow/main.py --debug  (saves annotated frames)

Tested: 2026-05-12 on Mini Pupper (RPi, OpenCV 4.10, camera /dev/video0)
"""

import sys
import os
import time
import signal
import argparse

import cv2
import numpy as np

sys.path.insert(0, os.path.expanduser("~/minipupper-app"))
from robot.continuous_control import ContinuousController

RUNNING = True


def rising_edge(button, hold=0.05, gap=0.15):
    pub.send({**MSG, button: True})
    time.sleep(hold)
    pub.send({**MSG, button: False})
    time.sleep(gap)


def signal_handler(sig, frame):
    global RUNNING
    print("\n[person-follow] Interrupted, shutting down...")
    RUNNING = False


def init_robot():
    """Activate the robot and raise to standing position."""
    print("[person-follow] Activating robot...")
    rising_edge("L1")
    time.sleep(0.15)
    # Raise body
    for _ in range(10):
        pub.send({**MSG, "dpady": 0.5})
        time.sleep(0.05)
    pub.send({**MSG, "dpady": 0})
    time.sleep(0.1)
    # Enter trot mode
    print("[person-follow] Entering trot mode...")
    rising_edge("R1")
    time.sleep(0.2)
    print("[person-follow] Robot ready.")


def shutdown_robot():
    """Stop movement and deactivate robot."""
    print("[person-follow] Stopping robot...")
    pub.send({**MSG, "lx": 0, "ly": 0, "rx": 0, "ry": 0, "dpadx": 0, "dpady": 0})
    time.sleep(0.1)
    # Exit trot
    rising_edge("R1", gap=0.2)
    # Deactivate
    rising_edge("L1")
    print("[person-follow] Robot deactivated.")


def send_velocity(lx=0.0, ly=0.0, rx=0.0, ry=0.0):
    global ctrl
    """Send velocity / posture command via UDP."""
    pub.send({**MSG, "lx": lx, "ly": ly, "rx": rx, "ry": ry})


def main():
    global RUNNING

    parser = argparse.ArgumentParser(
        description="Mini Pupper Camera Person Follow"
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="Save annotated debug frames to /tmp/person_follow/"
    )
    parser.add_argument(
        "--camera-id", type=int, default=0,
        help="Camera device ID (default 0)"
    )
    parser.add_argument(
        "--max-speed", type=float, default=0.35,
        help="Maximum forward/back speed (0-1, default 0.35)"
    )
    parser.add_argument(
        "--steer-gain", type=float, default=1.2,
        help="Steering response gain (default 1.2)"
    )
    parser.add_argument(
        "--follow-distance", type=float, default=0.35,
        help="Target person height ratio in frame (default 0.35)"
    )
    parser.add_argument(
        "--lost-frames", type=int, default=30,
        help="Frames without detection before stopping (default 30)"
    )
    args = parser.parse_args()

    signal.signal(signal.SIGINT, signal_handler)

    # HOG people detector
    hog = cv2.HOGDescriptor()
    hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

    # Open camera
    cap = cv2.VideoCapture(args.camera_id)
    if not cap.isOpened():
        print(f"[person-follow] ERROR: Cannot open camera {args.camera_id}", file=sys.stderr)
        sys.exit(1)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    # Warm up camera
    for _ in range(5):
        cap.read()
        time.sleep(0.1)

    debug_dir = None
    if args.debug:
        debug_dir = "/tmp/person_follow"
        os.makedirs(debug_dir, exist_ok=True)
        print(f"[person-follow] Debug frames saved to {debug_dir}/")

    # Initialize robot
    init_robot()

    lost_counter = 0
    MAX_LOST = args.lost_frames
    dt = UPDATE_INTERVAL
    frame_count = 0

    # PID state for smoother steering
    integral = 0.0
    prev_error = 0.0
    KP = args.steer_gain
    KI = 0.5
    KD = 0.3

    print("[person-follow] Person-following active. Press Ctrl+C to stop.")

    while RUNNING:
        ret, frame = cap.read()
        if not ret:
            print("[person-follow] Camera read failed, retrying...")
            time.sleep(0.1)
            continue

        frame_count += 1
        h, w = frame.shape[:2]

        # Downscale for faster detection
        scale = 0.5
        small = cv2.resize(frame, (int(w * scale), int(h * scale)))
        sh, sw = small.shape[:2]

        # Detect people
        (rects, _weights) = hog.detectMultiScale(
            small, winStride=(4, 4), padding=(8, 8), scale=1.05
        )

        # Pick the closest person (largest bounding box)
        best_rect = None
        best_area = 0
        for (x, y, rw, rh) in rects:
            area = rw * rh
            if area > best_area:
                best_area = area
                best_rect = (x, y, rw, rh)

        if best_rect is not None:
            lost_counter = 0
            bx, by, bw, bh = best_rect

            # Normalize coordinates to [0, 1]
            cx = (bx + bw / 2) / sw   # 0 = left, 1 = right
            cy = (by + bh / 2) / sh   # 0 = top, 1 = bottom
            person_height_ratio = bh / sh

            # Error from center
            error_x = cx - 0.5   # +right, -left

            # Steering: PID on lateral error
            integral += error_x * dt
            integral = np.clip(integral, -0.5, 0.5)
            derivative = (error_x - prev_error) / dt if dt > 0 else 0
            steer_cmd = KP * error_x + KI * integral + KD * derivative
            steer_cmd = np.clip(steer_cmd, -1.0, 1.0)
            prev_error = error_x

            # Forward/back based on person height ratio vs target distance
            # Bigger person = closer → back up; Smaller = farther → go forward
            dist_error = -(person_height_ratio - args.follow_distance)
            forward_cmd = np.clip(dist_error * 1.5, -args.max_speed, args.max_speed)

            # Send velocity command
            send_velocity(lx=steer_cmd, ly=forward_cmd)

            if frame_count % 10 == 0:
                print(
                    f"[person-follow] Person at ({cx:.2f}, {cy:.2f}) "
                    f"height={person_height_ratio:.2f} "
                    f"steer={steer_cmd:.2f} speed={forward_cmd:.2f}"
                )

            # Debug annotation
            if debug_dir and frame_count % 5 == 0:
                # Scale rect back to full res
                fx, fy, fw, fh = [int(v / scale) for v in (bx, by, bw, bh)]
                cv2.rectangle(frame, (fx, fy), (fx + fw, fy + fh), (0, 255, 0), 2)
                cv2.circle(frame, (w // 2, h // 2), 5, (0, 0, 255), -1)
                cv2.putText(
                    frame,
                    f"steer={steer_cmd:.2f} speed={forward_cmd:.2f}",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2,
                )
                cv2.imwrite(f"{debug_dir}/frame_{frame_count:06d}.jpg", frame)

        else:
            lost_counter += 1
            if lost_counter >= MAX_LOST:
                # Person lost for too long - stop
                send_velocity(0,0,0,0)  # stop via FPC
                if lost_counter == MAX_LOST:
                    print(f"[person-follow] Person lost for {MAX_LOST} frames. Stopped.")
                if lost_counter >= MAX_LOST + 30:
                    print("[person-follow] Person still not found. Exiting.")
                    break
            elif lost_counter == 1:
                # Just lost - immediately stop forward motion but keep steering
                pub.send({**MSG, "lx": 0, "ly": 0})

        time.sleep(dt)

    # Cleanup
    cap.release()
    shutdown_robot()

    print(f"[person-follow] Ran {frame_count} frames, "
          f"person seen in {frame_count - max(0, lost_counter - MAX_LOST - 30)} frames estimation.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
