#!/usr/bin/env python3
"""
Mini Pupper Robot Control Script
Uses the FPC (Flexible Programmable Choreography) API from StanfordQuadruped.
This replaces the buggy UDP-joystick-based minipupper_control.py.

The FPC API builds a MovementLib (a playlist of choreographed movements)
and executes them through the direct Controller + HardwareInterface path.

Usage:
  python3 robot/robot_control.py forward 1.0
  python3 robot/robot_control.py backward 2.0
  python3 robot/robot_control.py right 1.5
  python3 robot/robot_control.py left 0.5
  python3 robot/robot_control.py cw                  # rotate clockwise 30deg
  python3 robot/robot_control.py ccw 45              # rotate CCW 45deg
  python3 robot/robot_control.py look-up
  python3 robot/robot_control.py look-down
  python3 robot/robot_control.py look-right
  python3 robot/robot_control.py look-left
  python3 robot/robot_control.py raise-body          # ascend 3cm
  python3 robot/robot_control.py lower-body          # descend 3cm
  python3 robot/robot_control.py activate            # stand up
  python3 robot/robot_control.py deactivate          # sit down
  python3 robot/robot_control.py stop                # return to idle
  python3 robot/robot_control.py dance               # run a dance sequence
  python3 robot/robot_control.py greet               # wave a leg
"""

import sys
import time
import argparse
import numpy as np

# ── Add StanfordQuadruped to path ───────────────────────────────
sys.path.insert(0, "/home/ubuntu/StanfordQuadruped")

from src.MovementGroup import MovementGroups
from src.MovementScheme import MovementScheme
from src.Controller import Controller
from src.State import State
from src.Command import Command
from MangDang.mini_pupper.HardwareInterface import HardwareInterface
from MangDang.mini_pupper.Config import Configuration
from MangDang.mini_pupper.display import Display
from pupper.Kinematics import four_legs_inverse_kinematics

# ── Global hardware objects (reused across runs) ────────────────
_config = Configuration()
_hardware = HardwareInterface()
_controller = Controller(_config, four_legs_inverse_kinematics)
_state = State()
_display = Display()


# ═══════════════════════════════════════════════════════════════════
#  MovementLib Builders
# ═══════════════════════════════════════════════════════════════════

def _build_movement(command: str, duration: float, angle: float):
    """
    Build a MovementLib list for a single command.

    Args:
        command: Movement name (forward, backward, etc.)
        duration: How long to execute (seconds)
        angle: Angle for rotation commands (degrees)

    Returns:
        List of Movement objects (MovementLib)
    """
    move = MovementGroups()

    # ── Linear Movement (Level 2: gait_uni) ──
    # v_x: forward velocity (m/s, + = forward)
    # v_y: lateral velocity (m/s, + = left)
    # speed caps: vxcap=0.5, vycap=0.5
    SPEED = 0.2  # m/s, conservative default
    ACCEL = 0.3  # seconds to reach speed

    if command in ("forward", "f"):
        move.gait_uni(v_x=SPEED, v_y=0, time_uni=duration, time_acc=ACCEL)

    elif command in ("backward", "b"):
        move.gait_uni(v_x=-SPEED, v_y=0, time_uni=duration, time_acc=ACCEL)

    elif command in ("right", "r"):
        move.gait_uni(v_x=0, v_y=-SPEED, time_uni=duration, time_acc=ACCEL)

    elif command in ("left", "l"):
        move.gait_uni(v_x=0, v_y=SPEED, time_uni=duration, time_acc=ACCEL)

    # ── Rotation ──
    elif command in ("cw", "rotate_cw", "turn_right"):
        move.rotate(angle=(angle if angle else 30))

    elif command in ("ccw", "rotate_ccw", "turn_left"):
        move.rotate(angle=-(angle if angle else 30))

    # ── Posture (Level 2) ──
    elif command in ("look-up", "look_up"):
        move.look_up()

    elif command in ("look-down", "look_down"):
        move.look_down()

    elif command in ("look-right", "look_right"):
        move.look_right()

    elif command in ("look-left", "look_left"):
        move.look_left()

    elif command in ("look-upper-left", "look_upperleft", "upper-left", "upperleft"):
        move.look_upperleft()

    elif command in ("look-upper-right", "look_upperright", "upper-right", "upperright"):
        move.look_upperright()

    elif command in ("raise-body", "raise_body", "raise"):
        move.height_move(ht=0.03, time_uni=max(duration, 0.5), time_acc=0.5)

    elif command in ("lower-body", "lower_body", "lower"):
        move.height_move(ht=-0.03, time_uni=max(duration, 0.5), time_acc=0.5)

    elif command in ("body-row", "body_row", "roll"):
        move.body_row(row_deg=angle if angle else 10, time_uni=1.0, time_acc=0.5)

    # ── Standing / Activation ──
    elif command in ("stop", "idle"):
        move.stop(time=max(duration, 1.0))

    elif command in ("activate", "init", "stand"):
        move.height_move(ht=0.03, time_uni=0.5, time_acc=0.5)
        move.stop(time=0.3)

    elif command in ("deactivate", "sit", "rest"):
        move.height_move(ht=-0.04, time_uni=0.5, time_acc=0.5)
        move.stop(time=0.3)

    # ── Sequences ──
    elif command == "dance":
        move.move_forward()
        move.move_backward()
        move.move_right()
        move.move_left()
        move.look_up()
        move.look_down()
        move.rotate(angle=90)
        move.rotate(angle=-90)

    elif command == "greet":
        move.foreleg_lift("right", ht=0.04, time_uni=1.0, time_acc=0.5)
        move.stop(time=0.5)
        move.foreleg_lift("left", ht=0.04, time_uni=1.0, time_acc=0.5)
        move.stop(time=0.5)

    else:
        raise ValueError(f"Unknown command: {command}")

    return move.MovementLib


# ═══════════════════════════════════════════════════════════════════
#  Execution Engine
# ═══════════════════════════════════════════════════════════════════

def run_movement(movement_lib, timeout=30.0):
    """
    Execute a MovementLib directly on the robot hardware.

    This is the same control loop that run_danceActionList.py uses.
    Falls back to time-based exit if tick counting doesn't terminate.

    Args:
        movement_lib: List of Movements (from MovementGroups)
        timeout: Maximum wall-clock execution time (seconds)

    Returns:
        True on success, False on timeout/error
    """
    movement_ctl = MovementScheme(movement_lib)
    lib_length = len(movement_lib)

    command = Command()
    command.pseudo_dance_event = True

    last_loop = time.time()
    start_time = time.time()

    # Estimate duration from movement params + 3s safety margin
    est_duration = 10.0  # default fallback
    if lib_length > 0:
        try:
            from src.MovementGroup import MovementGroups
            est_duration = 15.0  # safe overestimate for most sequences
        except Exception:
            pass
    hard_timeout = min(timeout, max(est_duration, 8.0))

    while True:
        now = time.time()
        if now - last_loop < _config.dt:
            continue
        last_loop = now

        elapsed = now - start_time

        # Safety timeout
        if elapsed > hard_timeout:
            print(f"ERROR: Execution timed out after {elapsed:.1f}s", file=sys.stderr)
            return False

        # Orientation (no IMU for CLI commands)
        _state.quat_orientation = np.array([1, 0, 0, 0])

        # Advance the movement scheme by one tick
        movement_ctl.runMovementScheme()

        # Populate command from current movement state
        command.legslocation = movement_ctl.getMovemenLegsLocation()
        command.horizontal_velocity = movement_ctl.getMovemenSpeed()
        command.roll = movement_ctl.attitude_now[0]
        command.pitch = movement_ctl.attitude_now[1]
        command.yaw = movement_ctl.attitude_now[2]
        command.yaw_rate = movement_ctl.getMovemenTurn()

        # Run inverse kinematics + controller
        _controller.run(_state, command, _display)

        # Send joint angles to servos via ESP32
        _hardware.set_actuator_postions(_state.joint_angles)

        # Check if all movements played (tick logic) OR time-based fallback
        scheme_done = (movement_ctl.movement_now_number >= lib_length - 1
                       and movement_ctl.tick >= movement_ctl.now_ticks)
        time_done = elapsed >= est_duration - 2.0

        if scheme_done or time_done:
            break

    return True


# ═══════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Mini Pupper Robot Control (FPC API)"
    )
    parser.add_argument(
        "command",
        nargs="*",
        help="Command and optional arguments: {cmd} {duration|angle}",
    )
    parser.add_argument(
        "--duration", type=float, default=1.0,
        help="Duration in seconds (default: 1.0, for movement commands)",
    )
    parser.add_argument(
        "--angle", type=float, default=None,
        help="Angle in degrees (for rotation/roll commands)",
    )
    parser.add_argument(
        "--list", action="store_true", dest="list_cmds",
        help="List all available commands",
    )

    args = parser.parse_args()

    if args.list_cmds:
        print("Available commands:")
        print("  forward, backward, right, left          # Movement (arg: duration)")
        print("  cw, ccw                                  # Rotate (arg: degrees)")
        print("  look-up, look-down, look-left, look-right")
        print("  raise-body, lower-body                   # Height (arg: duration)")
        print("  body-row, roll                           # Body roll (arg: degrees)")
        print("  activate, deactivate, stop               # Standing")
        print("  dance, greet                             # Sequences")
        return 0

    if not args.command:
        parser.print_help()
        return 1

    cmd = args.command[0]
    duration = args.duration
    angle = args.angle

    # Parse positional arguments for convenience
    if len(args.command) >= 2:
        try:
            val = float(args.command[1])
            # Determine if it's a duration or angle based on command
            if cmd in ("cw", "ccw", "rotate_cw", "rotate_ccw",
                       "body-row", "body_row", "roll"):
                angle = val
            else:
                duration = val
        except ValueError:
            pass

    try:
        print(f"Building movement: {cmd} (duration={duration}s, angle={angle})")
        lib = _build_movement(cmd, duration, angle)
        print(f"MovementLib: {len(lib)} action(s)")
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print("Executing...")
    success = run_movement(lib)

    if success:
        print(f"ok: {cmd}")
        return 0
    else:
        print(f"FAIL: {cmd}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
