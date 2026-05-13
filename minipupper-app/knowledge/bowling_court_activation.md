# Bowling Court Activation — Exploration

## Request
User asked to "have a bowling Court activate" — a bowling-themed robot action.

## Hardware Available
- Quadruped robot (Mini Pupper) with trot gait
- Body roll via dpadx (+1 right roll, -1 left roll)
- Body height via dpady (+1 raise, -1 lower)
- Head pitch via ry (+1 look up, -1 look down)
- Head yaw via rx (+1 look right, -1 look left)
- UDP joystick port 8830 for all commands

## What "Bowling Court Activate" Means
A robot can't physically bowl, but it can simulate a bowling action:

1. **The Approach** — Robot trots forward (~1s) as the approach step
2. **The Swing** — Robot rolls body left then right (simulating arm swing)
3. **The Release** — Robot crouches briefly (lowers body)
4. **The Follow-Through** — Robot looks up toward where the ball went
5. **Celebration** — Mini dance or standing pose

## Feasibility Assessment
**Feasible** — All movements available via UDP joystick protocol:
- R1 pulse → trot mode
- ly: 1.0 for 1s → forward approach
- dpadx: -1 then dpadx: 1 → body roll (swing)
- dpady: -1 → crouch (release)
- ry: 1.0 → look up (follow-through)
- Activated via standard L1 → R1 sequence

## Related Knowledge
- Camera available for visual flair but not needed
- No ML needed — pure MovementGroup + UDP joystick
- Movement bug exists in move_api.py (see movement_bug fix)
