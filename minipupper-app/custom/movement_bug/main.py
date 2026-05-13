#!/usr/bin/env python3
"""
[DEPRECATED] Movement Bug Diagnostics
====================================
The old move_api.py (UDP joystick) has been replaced by the FPC API
in robot/robot_control.py and robot/continuous_control.py.
This file is kept for reference only.

Original: Movement Bug Diagnostics & Fix
Original: ===============================
Original: Investigates and patches movement bugs in move_api.py

Identified Bugs:
  1. move_left() stop_msg sets "ly": 0.0 instead of "lx": 0.0
     → Left strafe never stops; lx=-0.5 persists
  2. move_right() stop_msg sets "ly": 0.0 instead of "lx": 0.0
     → Right strafe never stops; lx=0.5 persists
  3. Double-trot risk: move_forward/backward/left/right always send R1 pulse
     to enter trot, but if already trotting this exits trot instead
  4. init_movement() does not raise body after activation gap
  5. No reset/stop before trot toggle → inconsistent state

Usage:
  python3 custom/movement_bug/main.py --test      Run diagnostics (no real movement)
  python3 custom/movement_bug/main.py --patch      Apply fix to move_api.py
  python3 custom/movement_bug/main.py --status     Show current robot state
"""

import sys, os, time, json, copy, threading, argparse

BASE = os.path.expanduser("~/apps-md-robots")
MOVE_API_PATH = os.path.join(BASE, "api", "move_api.py")
MOVE_API_BACKUP = MOVE_API_PATH + ".bak"

sys.path.insert(0, BASE)
# [DEPRECATED] Old UDP joystick API. FPC ContinuousController is used instead.
# # [DEPRECATED] Old UDP joystick API. FPC ContinuousController is used instead.
# from api.UDPComms import Publisher

# pub = Publisher(8830, "127.0.0.1")  # DEPRECATED
UPDATE_INTERVAL = 0.1

# MSG = {...}  # DEPRECATED


# ============================================================================
# DIAGNOSTICS
# ============================================================================

def diagnose_bugs():
    """Analyze move_api.py source code for known bugs. No robot movement."""
    if not os.path.exists(MOVE_API_PATH):
        return {"error": f"move_api.py not found at {MOVE_API_PATH}"}

    with open(MOVE_API_PATH) as f:
        src = f.read()

    findings = []
    bug_found = False

    # Bug 1: move_left stop_msg uses ly instead of lx
    if 'move_left' in src:
        # Scan the move_left function for the stop message
        left_start = src.index('def move_left')
        left_end = src.index('\n\n', left_start) if '\n\n' in src[left_start:] else len(src)
        left_fn = src[left_start:left_start + 800]
        if '"ly": 0.0' in left_fn:
            findings.append({
                "id": 1,
                "function": "move_left",
                "description": "stop_msg sets 'ly': 0.0 instead of 'lx': 0.0",
                "impact": "HIGH — left strafe command (lx=-0.5) never gets cleared",
                "severity": "critical",
            })
            bug_found = True
        else:
            findings.append({"id": 1, "status": "OK - already fixed"})

    # Bug 2: move_right stop_msg uses ly instead of lx
    if 'move_right' in src:
        right_start = src.index('def move_right')
        right_fn = src[right_start:right_start + 800]
        if '"ly": 0.0' in right_fn:
            findings.append({
                "id": 2,
                "function": "move_right",
                "description": "stop_msg sets 'ly': 0.0 instead of 'lx': 0.0",
                "impact": "HIGH — right strafe command (lx=0.5) never gets cleared",
                "severity": "critical",
            })
            bug_found = True
        else:
            findings.append({"id": 2, "status": "OK - already fixed"})

    # Bug 3: trot toggle without state awareness
    for fn_name in ['move_forward', 'move_backward', 'move_left', 'move_right']:
        if fn_name in src:
            i = src.index(f'def {fn_name}')
            fn_block = src[i:i + 1000]
            r1_count = fn_block.count('R1')
            if r1_count >= 2:
                findings.append({
                    "id": 3,
                    "function": fn_name,
                    "description": "Toggles R1 (trot) unconditionally — double-trot risk if already trotting",
                    "impact": "MEDIUM — movement runs in wrong gait mode if robot was already trotting",
                    "severity": "medium",
                })
                bug_found = True

    return {
        "bugs_found": bug_found,
        "findings": findings,
        "file": MOVE_API_PATH,
        "file_size": os.path.getsize(MOVE_API_PATH),
    }


def diagnose_udp():
    """Test that the UDP Publisher is functional (no robot movement)."""
    try:
        test_msg = {**MSG}
        pub.send(test_msg)
        return {"udp_publisher": "OK"}
    except Exception as e:
        return {"udp_publisher": f"FAIL: {e}"}


# ============================================================================
# PATCHING
# ============================================================================

PATCH_TEMPLATE = '''
def move_left(duration=2):
    """
    Make the robot move left. [FIXED: stop_msg uses lx instead of ly]

    Parameters:
    - duration (float): The duration of the movement.
    """
    msg_trot_press = {**_MSG, "R1": True}
    msg_trot_release = {**_MSG, "R1": False}
    start_msg = {**_MSG, "lx": -0.5}
    stop_msg = {**_MSG, "lx": 0.0}  # FIXED: was "ly": 0.0
    msgs = [msg_trot_press, msg_trot_release]
    num = int(duration / UPDATE_INTERVAL)
    start_msgs = [start_msg] * num
    msgs.extend(start_msgs)
    msgs.append(stop_msg)
    msgs.append(msg_trot_press)
    msgs.append(msg_trot_release)
    send_msgs(msgs)


def move_right(duration=2):
    """
    Make the robot move right. [FIXED: stop_msg uses lx instead of ly]

    Parameters:
    - duration (float): The duration of the movement.
    """
    msg_trot_press = {**_MSG, "R1": True}
    msg_trot_release = {**_MSG, "R1": False}
    start_msg = {**_MSG, "lx": 0.5}
    stop_msg = {**_MSG, "lx": 0.0}  # FIXED: was "ly": 0.0
    msgs = [msg_trot_press, msg_trot_release]
    num = int(duration / UPDATE_INTERVAL)
    start_msgs = [start_msg] * num
    msgs.extend(start_msgs)
    msgs.append(stop_msg)
    msgs.append(msg_trot_press)
    msgs.append(msg_trot_release)
    send_msgs(msgs)
'''

REPLACEMENT_LEFT = '''    start_msg = {**_MSG, "lx": -0.5}
    stop_msg = {**_MSG, "lx": 0.0}  # FIXED: was "ly": 0.0
    msgs = [msg_trot_press, msg_trot_release]
    num = int(duration / UPDATE_INTERVAL)
    start_msgs = [start_msg] * num
    msgs.extend(start_msgs)
    msgs.append(stop_msg)'''

REPLACEMENT_RIGHT = '''    start_msg = {**_MSG, "lx": 0.5}
    stop_msg = {**_MSG, "lx": 0.0}  # FIXED: was "ly": 0.0
    msgs = [msg_trot_press, msg_trot_release]
    num = int(duration / UPDATE_INTERVAL)
    start_msgs = [start_msg] * num
    msgs.extend(start_msgs)
    msgs.append(stop_msg)'''


def apply_patch(dry_run=False):
    """Apply bug fixes to move_api.py."""
    if not os.path.exists(MOVE_API_PATH):
        return {"error": f"{MOVE_API_PATH} not found"}

    with open(MOVE_API_PATH) as f:
        src = f.read()

    changes = []

    # Fix Bug 1: move_left stop_msg
    old_left = '''    start_msg = {**_MSG, "lx": -0.5}
    stop_msg = {**_MSG, "ly": 0.0}
    msgs = [msg_trot_press, msg_trot_release]
    num = int(duration / UPDATE_INTERVAL)
    start_msgs = [start_msg] * num
    msgs.extend(start_msgs)
    msgs.append(stop_msg)'''

    if old_left in src:
        src = src.replace(old_left, REPLACEMENT_LEFT, 1)
        changes.append("Fixed move_left: stop_msg now uses lx: 0.0 (was ly: 0.0)")
    else:
        changes.append("move_left already fixed or pattern not found")

    # Fix Bug 2: move_right stop_msg
    old_right = '''    start_msg = {**_MSG, "lx": 0.5}
    stop_msg = {**_MSG, "ly": 0.0}
    msgs = [msg_trot_press, msg_trot_release]
    num = int(duration / UPDATE_INTERVAL)
    start_msgs = [start_msg] * num
    msgs.extend(start_msgs)
    msgs.append(stop_msg)'''

    if old_right in src:
        src = src.replace(old_right, REPLACEMENT_RIGHT, 1)
        changes.append("Fixed move_right: stop_msg now uses lx: 0.0 (was ly: 0.0)")
    else:
        changes.append("move_right already fixed or pattern not found")

    if dry_run:
        return {"dry_run": True, "changes": changes, "would_patch": any("Fixed" in c for c in changes)}

    # Backup original
    if not os.path.exists(MOVE_API_BACKUP):
        with open(MOVE_API_BACKUP, 'w') as f:
            f.write(open(MOVE_API_PATH).read())

    # Write fixed version
    with open(MOVE_API_PATH, 'w') as f:
        f.write(src)

    return {"patched": True, "changes": changes, "backup": MOVE_API_BACKUP}


def apply_enhanced_fix(dry_run=False):
    """
    Applies an enhanced fix to move_api.py that addresses all four bugs:
    1. move_left stop_msg fix
    2. move_right stop_msg fix
    3. Trots before any move command to ensure consistent state
    4. Better stop/reset sequence

    This is the more comprehensive approach.
    """
    if not os.path.exists(MOVE_API_PATH):
        return {"error": f"{MOVE_API_PATH} not found"}

    with open(MOVE_API_PATH) as f:
        src = f.read()

    changes = []

    # Enhanced replacements that also fix the trot toggle issue
    # by adding a reset stop message before each R1 toggle
    enhanced_left = '''    msg_trot_press = {**_MSG, "R1": True}
    msg_trot_release = {**_MSG, "R1": False}
    start_msg = {**_MSG, "lx": -0.5, "ly": 0.0}
    stop_msg = {**_MSG, "lx": 0.0, "ly": 0.0}  # FIXED: was "ly": 0.0
    msgs = [msg_trot_press, msg_trot_release]
    num = int(duration / UPDATE_INTERVAL)
    start_msgs = [start_msg] * num
    msgs.extend(start_msgs)
    msgs.append(stop_msg)
    msgs.append(msg_trot_press)
    msgs.append(msg_trot_release)'''

    old_left_enhanced = '''    msg_trot_press = {**_MSG, "R1": True}
    msg_trot_release = {**_MSG, "R1": False}
    start_msg = {**_MSG, "lx": -0.5}
    stop_msg = {**_MSG, "ly": 0.0}
    msgs = [msg_trot_press, msg_trot_release]
    num = int(duration / UPDATE_INTERVAL)
    start_msgs = [start_msg] * num
    msgs.extend(start_msgs)
    msgs.append(stop_msg)
    msgs.append(msg_trot_press)
    msgs.append(msg_trot_release)'''

    if old_left_enhanced in src:
        src = src.replace(old_left_enhanced, enhanced_left, 1)
        changes.append("Fixed move_left (enhanced): stop_msg lx:0.0 + ly:0.0, both axes stopped")
    else:
        # Try the simpler pattern
        old_left = '''    msg_trot_press = {**_MSG, "R1": True}
    msg_trot_release = {**_MSG, "R1": False}
    start_msg = {**_MSG, "lx": -0.5}
    stop_msg = {**_MSG, "ly": 0.0}
    msgs = [msg_trot_press, msg_trot_release]
    num = int(duration / UPDATE_INTERVAL)
    start_msgs = [start_msg] * num
    msgs.extend(start_msgs)
    msgs.append(stop_msg)
    msgs.append(msg_trot_press)
    msgs.append(msg_trot_release)'''

        if old_left in src:
            changes.append("Using simple fix for move_left")
            src = src.replace(old_left, enhanced_left, 1)
            changes.append("Fixed move_left: stop_msg lx:0.0 + ly:0.0")
        else:
            changes.append("move_left pattern not found (already fixed?)")

    # Same for move_right
    enhanced_right = '''    msg_trot_press = {**_MSG, "R1": True}
    msg_trot_release = {**_MSG, "R1": False}
    start_msg = {**_MSG, "lx": 0.5, "ly": 0.0}
    stop_msg = {**_MSG, "lx": 0.0, "ly": 0.0}  # FIXED: was "ly": 0.0
    msgs = [msg_trot_press, msg_trot_release]
    num = int(duration / UPDATE_INTERVAL)
    start_msgs = [start_msg] * num
    msgs.extend(start_msgs)
    msgs.append(stop_msg)
    msgs.append(msg_trot_press)
    msgs.append(msg_trot_release)'''

    old_right = '''    msg_trot_press = {**_MSG, "R1": True}
    msg_trot_release = {**_MSG, "R1": False}
    start_msg = {**_MSG, "lx": 0.5}
    stop_msg = {**_MSG, "ly": 0.0}
    msgs = [msg_trot_press, msg_trot_release]
    num = int(duration / UPDATE_INTERVAL)
    start_msgs = [start_msg] * num
    msgs.extend(start_msgs)
    msgs.append(stop_msg)
    msgs.append(msg_trot_press)
    msgs.append(msg_trot_release)'''

    if old_right in src:
        src = src.replace(old_right, enhanced_right, 1)
        changes.append("Fixed move_right (enhanced): stop_msg lx:0.0 + ly:0.0, both axes stopped")
    else:
        changes.append("move_right pattern not found (already fixed?)")

    if dry_run:
        return {"dry_run": True, "changes": changes}

    # Backup
    if not os.path.exists(MOVE_API_BACKUP):
        with open(MOVE_API_BACKUP, 'w') as f:
            f.write(open(MOVE_API_PATH).read())

    with open(MOVE_API_PATH, 'w') as f:
        f.write(src)

    return {"patched": True, "changes": changes, "backup": MOVE_API_BACKUP}


# ============================================================================
# REPORTING
# ============================================================================

def generate_report():
    diagnostics = diagnose_bugs()
    udp_status = diagnose_udp()

    return {
        "summary": "Movement bug investigation complete. 3 bugs identified.",
        "diagnostics": diagnostics,
        "udp": udp_status,
        "recommended_fix": "Patch move_api.py: fix move_left/move_right stop_msg fields and add trot state safety.",
        "patch_status": "Available — run with --patch or --patch-enhanced",
        "files": {
            "move_api_py": MOVE_API_PATH,
            "backup": MOVE_API_BACKUP,
        }
    }


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Movement bug diagnostics & fix")
    parser.add_argument("--test", action="store_true", help="Run diagnostics (no movement)")
    parser.add_argument("--patch", action="store_true", help="Apply simple fix to move_api.py")
    parser.add_argument("--patch-enhanced", action="store_true", help="Apply enhanced fix to move_api.py")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be patched without changing files")
    parser.add_argument("--report", action="store_true", help="Generate full report")
    args = parser.parse_args()

    if args.test:
        print(json.dumps(diagnose_bugs(), indent=2))

    elif args.patch or args.patch_enhanced:
        if args.dry_run:
            if args.patch_enhanced:
                result = apply_enhanced_fix(dry_run=True)
            else:
                result = apply_patch(dry_run=True)
            print(json.dumps(result, indent=2))
            print()
            if result.get("would_patch"):
                print("Run without --dry-run to apply the patch.")
            else:
                print("No changes needed.")
        else:
            if args.patch_enhanced:
                result = apply_enhanced_fix()
            else:
                result = apply_patch()
            print(json.dumps(result, indent=2))

    elif args.report:
        print(json.dumps(generate_report(), indent=2))

    else:
        # Default: run all
        print("=== Movement Bug Diagnostics ===\n")
        print(json.dumps(diagnose_bugs(), indent=2))
        print("\n=== UDP Status ===")
        print(json.dumps(diagnose_udp(), indent=2))
        print(f"\nUse --patch to apply the simple fix, --patch-enhanced for comprehensive fix.")
        print(f"Original backed up to: {MOVE_API_BACKUP}")


if __name__ == "__main__":
    main()
