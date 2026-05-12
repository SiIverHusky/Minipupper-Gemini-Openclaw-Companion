# Phase 3 — Complex & Exploratory Tasks

**Status:** Design Document  
**Date:** 2026-05-12  
**Version:** 0.1 (Proposal)

---

## 1. The Gap

Phase 2 offloads **known, pre-defined actions** (web_search, robot.move_forward, etc.)
to the OpenClaw agent via `[TASK]` markers. If Gemini outputs an action that isn't
in the 19-item handler list, the agent returns "Unknown action."

**Phase 3 removes this constraint.** Gemini can now ask the agent to:
1. **Explore** — research a hardware capability, software library, or system feature
   and report findings back to the user
2. **Implement** — build a new capability from scratch, test it, and get user validation

This turns the agent from a **tool executor** into an **on-demand R&D engineer**.

---

## 2. Architecture Changes

### 2.1 New Action Types

| Action | Purpose | Example |
|--------|---------|---------|
| `explore` | Research a capability and report findings | "What can the camera do?" |
| `implement` | Build a new robot capability from scratch | "Follow the person in front of you" |

### 2.2 New Protocol Fields

```json
{
  "protocol": "minipupper-v1",
  "type": "task",
  "action": "explore",
  "params": {
    "goal": "What can the camera do?",
    "topic": "camera",
    "context": "The user wants to understand what camera features are available"
  },
  "userQuery": "What is the camera able to do?"
}
```

```json
{
  "protocol": "minipupper-v1",
  "type": "task",
  "action": "implement",
  "params": {
    "goal": "Person following using camera",
    "topic": "camera_person_follow",
    "context": "The user wants the robot to detect and follow a person visually",
    "attempt_id": 1,
    "feedback": null
  },
  "userQuery": "Use the camera to follow the person in front of you"
}
```

### 2.3 Knowledge Base File

The agent stores exploration results in a structured knowledge file that persists
across sessions and can be referenced by future tasks.

**File:** `~/minipupper-app/knowledge/INDEX.json`  
**Storage:** `~/minipupper-app/knowledge/{topic}.md`

INDEX.json maps topic names to their markdown files:

```json
{
  "camera": {
    "file": "knowledge/camera.md",
    "title": "Camera Capabilities",
    "summary": "MIPI CSI camera at /dev/video0, 640x480, OpenCV 4.10.0",
    "created": 1778580000.0,
    "updated": 1778580000.0,
    "implementations": ["person_follower", "object_detector"]
  },
  "imu": {
    "file": "knowledge/imu.md",
    "title": "IMU (Inertial Measurement Unit)",
    "summary": "Onboard IMU via ESP32, accelerometer + gyroscope data",
    "created": 1778580000.0,
    "updated": 1778580000.0,
    "implementations": []
  }
}
```

### 2.4 Custom Implementations

When the agent implements a new capability, it writes the code to:

```
~/minipupper-app/custom/{capability_name}/
  main.py          # Entry point (argparse-based, like minipupper_control.py)
  explore.md       # Notes from the exploration phase
  test_results.md  # Test results and user feedback
```

Each custom implementation is registered in `knowledge/INDEX.json` under
`implementations` so it can be referenced later.

---

## 3. Flow: Exploratory Task

### User: "What can the camera do?"

```
1. ASR → "What can the camera do?"
2. Gemini processes → decides to offload exploration
3. Gemini outputs:

   "Let me check what my camera is capable of!
    [TASK]{"protocol":"minipupper-v1","type":"task","action":"explore",
      "params":{"goal":"What can the camera do?","topic":"camera",
                "context":"The user wants to understand camera features"},
      "userQuery":"What can the camera do?"}[/TASK]"

4. App writes to tasks.json: status="pending"
5. App signals the agent (cron wake or session message)
6. Agent reads tasks.json, sees action="explore"
7. Agent explores:
   a. exec: check /dev/video0, try OpenCV capture, get resolution, FPS
   b. exec: check available video formats, check RGB vs grayscale
   c. Research: what could work with cv2 + numpy + scipy + sklearn (no torch)
   d. Web search: "OpenCV person detection without deep learning" if needed
8. Agent writes knowledge/camera.md with structured findings
9. Agent writes result to tasks.json (status="completed", result=summary)
10. TaskWatcher detects → Gemini TTS: "I have a MIPI CSI camera..."
11. Agent updates knowledge/INDEX.json
```

### Result of exploration (knowledge/camera.md):

```markdown
# Camera Capabilities

## Hardware
- Device: /dev/video0 (MIPI CSI camera)
- Driver: detected via v4l2, camera_auto_detect=1 in config.txt
- Resolution: tested at 640x480 (default from OpenCV)

## Software Stack
- OpenCV 4.10.0 (cv2) — full capture pipeline
- PIL 10.4.0 — image manipulation, display on ST7789 LCD
- numpy 1.26.4 — array operations

## Sensor Package Limitations
- No face_recognition module
- No TensorFlow / TFLite
- No PyTorch
- Available: scipy, sklearn (classification possible with HOG/SIFT+ SVM)
- MIPI camera works at /dev/video0, no picamera/picamera2 libraries

## What's Possible (no-dependency)
- Photo capture (demonstrated: capture_and_show.py)
- Video display on LCD
- Basic motion detection (frame differencing)
- Color tracking (HSV thresholding)
- Edge detection (Canny)

## What's Possible (with scipy/sklearn)
- HOG + SVM person detection (sliding window)
- Background subtraction + contour analysis
- Simple object tracking (CentroidTracker)

## Known Working Scripts
- capture_and_show.py - capture + display on LCD
```

---

## 4. Flow: Implementation Task

### User: "Use the camera to follow the person in front of you"

```
1. ASR → "Use the camera to follow the person in front of you"
2. Gemini processes → decides to offload implementation
3. Gemini outputs:

   "Let me see if I can do that!
    [TASK]{"protocol":"minipupper-v1","type":"task","action":"implement",
      "params":{"goal":"Person following using camera",
                "topic":"camera_person_follow",
                "context":"User wants visual person following",
                "attempt_id":1},
      "userQuery":"Use the camera to follow the person in front of you"}[/TASK]"

4. App writes to tasks.json: status="pending"
5. Agent reads tasks.json, sees action="implement"
6. Agent explores feasibility:
   a. Check knowledge/camera.md (already exists from previous exploration)
   b. Determine approach given constraints (no ML frameworks, cv2 only)
   c. Choose strategy: background subtraction + color tracking OR HOG detection
   d. Write prototype to ~/minipupper-app/custom/person_follower/main.py
   e. Test on the robot: exec python3 custom/person_follower/main.py
   f. Collect results
7. Agent writes test_results.md with observations
8. Agent updates task result:

   status="completed"
   result="I built a person follower prototype...<summary of approach, test results>"
   Also: result.feedback_required = true  (new field for user evaluation)

9. TaskWatcher detects → Gemini TTS: "I built a person follower..."
10. App asks user: "Did it work?" (via LLM follow-up)
11. User feedback goes to a new task with params.feedback and attempt_id=2
12. Agent iterates based on feedback
13. On success, registers in knowledge/INDEX.json under implementations
```

### Interaction with user after implementation:

The result text is fed back to Gemini, which generates a natural description.
The app then asks the user for evaluation. This is important because the
agent can't perceive success — only the human can judge if the robot
actually followed them.

---

## 5. System Prompt Changes

### New Section in system_prompt_phase2.txt

The prompt needs two new capabilities:

```
## Exploration tasks (ask the agent to research anything)
When the user asks about hardware capabilities, sensors, what's possible:
[TASK]{"protocol":"minipupper-v1","type":"task","action":"explore",
  "params":{"goal":"Describe what user asked about","topic":"topic-name",
            "context":"Full user query context"}}[/TASK]

Examples:
"Can the camera see in the dark?" → explore with topic="camera"
"Can you detect objects?" → explore with topic="camera"  
"Do you have sensors?" → explore with topic="sensors"
"What motors do you have?" → explore with topic="motors"
"Can you make coffee?" → explore with topic="general" (agent will check all)

## Implementation tasks (ask the agent to build new capabilities)
When the user asks for a new behavior not yet built:
[TASK]{"protocol":"minipupper-v1","type":"task","action":"implement",
  "params":{"goal":"What the user wants achieved",
            "topic":"topic-name",
            "context":"Full user request"}}[/TASK]

Examples:
"Follow me with the camera" → implement with topic="camera_person_follow"
"Detect when someone knocks" → implement with topic="knock_detection"
"Wave your leg when you see me" → implement with topic="greeting_wave"
```

### Rule Updates

```
- For explore tasks: say something like "Let me research that!" and offload
- For implement tasks: say something like "Let me try to build that!" and offload
- NEVER reject a request because "I don't know how" — offload to exploration instead
- If the user asks for a capability you're unsure about, always offload via explore
  or implement rather than guessing or refusing
```

---

## 6. Handler Changes (Gateway Side)

### New handler: `explore`

In `task_handler.py`:

```python
@router.register("explore")
def _handle_explore(task_id: str, params: dict,
                    send_status: Callable) -> dict:
    goal = params.get("goal", "")
    topic = params.get("topic", "general")
    context = params.get("context", "")

    send_status("researching", 10.0,
                f"Exploring: {goal}")

    return {
        "ok": True,
        "text": f"Exploring {topic}: {goal}",
        "requires_agent_exploration": True,
        "topic": topic,
        "goal": goal,
        "context": context,
    }
```

### New handler: `implement`

```python
@router.register("implement")
def _handle_implement(task_id: str, params: dict,
                      send_status: Callable) -> dict:
    goal = params.get("goal", "")
    topic = params.get("topic", "general")
    context = params.get("context", "")
    attempt_id = params.get("attempt_id", 1)
    feedback = params.get("feedback")

    send_status("planning", 5.0,
                f"Planning implementation: {goal}")

    return {
        "ok": True,
        "text": f"Implementing {topic}: {goal}",
        "requires_agent_implementation": True,
        "topic": topic,
        "goal": goal,
        "context": context,
        "attempt_id": attempt_id,
        "feedback": feedback,
    }
```

---

## 7. The Agent's Role

When the agent processes a Phase 3 task, it follows this flow:

### For `explore` tasks:

```
1. Read knowledge base (knowledge/INDEX.json) for existing info on topic
2. If found AND fresh (< 24h old) → use cached knowledge
3. Otherwise → run exploration commands on the Pi:
   a. Hardware checks (ls /dev/, v4l2, i2cdetect, etc.)
   b. Software checks (python3 -c "import X; print(...)")
   c. If needed: web_search for documentation
   d. Run any relevant test scripts
4. Compile findings into knowledge/{topic}.md
5. Write to file (via exec echo/write or node file access)
6. Update INDEX.json
7. Return result with summary text
```

### For `implement` tasks:

```
1. Read knowledge base for topic-related info
2. Explore feasibility (what libraries, what hardware, what works)
3. Design approach (multiple if-else based on what's available)
4. Write implementation code to custom/{topic}/
5. Test by running the script on the Pi
6. Report test results
7. Mark feedback_required=true if user evaluation needed
8. On subsequent attempts with feedback, iterate on the code
```

---

## 8. New Files and Structure

### On the Pi (`~/minipupper-app/`):

```
knowledge/
  INDEX.json               # Topic index (JSON)
  camera.md                # Camera capabilities
  imu.md                   # IMU sensor info
  battery.md               # Battery/ power
  motors.md                # Servo/motor info
  sensors.md               # All sensors combined

custom/
  person_follower/
    main.py                # Executable script
    explore.md             # Notes from exploration phase
    test_results.md        # Test logs and user feedback
  wave_greeting/
    main.py
    ...
```

### On the Gateway (`~/.openclaw/workspace/minipupper/`):

```
knowledge/                 # Mirrored/synced from Pi
```

---

## 9. Handling Feedback Loops

The key difference from Phase 2: **implementation tasks may need iterative feedback.**

Flow for iteration:

```
User: "Did it work?"
→ Gemini might not know — that's fine
→ But the TTS from the TaskWatcher will include "I tried..." in the result text
→ User responds with evaluation
→ Gemini creates a new implement task with feedback and attempt_id+1
```

A simpler approach: the agent writes feedback into the task result:

```json
{
  "taskId": "task-xxx",
  "status": "completed",
  "result": "Built person follower prototype. Approach: HSV tracking.",
  "requires_feedback": true,
  "feedback_question": "Did the robot follow you correctly?"
}
```

The app then has a mechanism to ask and relay feedback:
```
App → User: "Did the robot follow you correctly?"
User: "Sort of, but it lost me when I moved fast"
→ Gemini creates implement task with feedback included
```

---

## 10. What the App Needs to Handle Differently

1. **Longer task durations** — exploration and implementation can take
   30-60 seconds. The TaskWatcher should announce progress periodically
   ("Still researching...", "Now testing approach...")

2. **Feedback prompts** — when `requires_feedback` is set, the app should
   ask the user for evaluation after the result is announced.

3. **Knowledge awareness** — Gemini should know to check the knowledge
   base before asking for exploration (via system prompt mention).

---

## 11. Concrete Example

### Walking through "What can the camera do?"

**Pi exec exploration commands the agent runs:**

```bash
# Check camera device
ls -la /dev/video*

# Check resolution with OpenCV
python3 -c "
import cv2
cap = cv2.VideoCapture(0)
ret, frame = cap.read()
print(f'Resolution: {frame.shape}')
cap.release()
"

# Check available codecs
python3 -c "
import cv2
cap = cv2.VideoCapture(0)
fourcc = cv2.VideoWriter_fourcc(*'MJPG')
print(f'Backend: {cap.get(cv2.CAP_PROP_BACKEND)}')
print(f'Format: {cap.get(cv2.CAP_PROP_FORMAT)}')
cap.release()
"

# Check what ML might work
python3 -c "
import cv2
hog = cv2.HOGDescriptor()
print('HOG available:', hog)
"
```

**Result written to knowledge/camera.md** — structured markdown.

### Walking through "Follow me with the camera"

**After checking knowledge/camera.md, the agent might:**

```python
# Approach: Background subtraction + centroid tracking
# No ML libraries available, using pure OpenCV

import cv2
import numpy as np

cap = cv2.VideoCapture(0)
fgbg = cv2.createBackgroundSubtractorMOG2()

while True:
    ret, frame = cap.read()
    fgmask = fgbg.apply(frame)

    # Find contours
    contours, _ = cv2.findContours(fgmask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if contours:
        largest = max(contours, key=cv2.contourArea)
        x, y, w, h = cv2.boundingRect(largest)
        center_x = x + w//2
        frame_center = frame.shape[1] // 2

        # Map center_x to robot yaw command
        error = (center_x - frame_center) / frame_center  # -1 to 1

        # Send to robot via UDP publisher
        # ... (uses minipupper_control.py hold/edge commands)
```

**Agent tests this, reports:**
- "Can detect moving objects but person following is jittery"
- "No face/people detection available without DL frameworks"
- "Color tracking approach may work if person wears distinctive color"

---

## 12. Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Exploration generates unsafe exec commands | Agent must validate all commands before running; no `rm -rf`, no `sudo` without caution |
| Implementation code could damage robot | Implementations go to `custom/` directory, not system paths; user must opt-in to run |
| Feedback loops never terminate | Set max_attempts=3 per implementation task |
| Knowledge file grows stale | `explore` tasks read INDEX.json first; only re-explore if >24h old |
| Gemini hallucinates capability descriptions | Agent includes verification evidence in knowledge files ("verified: camera captures at 640x480") |
| Long tasks (30-60s) starve regular work | Tasks have timeout (default 120s); TaskWatcher shows progress updates |

---

## 13. Implementation Order

1. **System prompt** — Add explore/implement categories to `system_prompt_phase2.txt`
2. **Task handler** — Add `explore` and `implement` handler stubs to `task_handler.py`
3. **Knowledge storage** — Create `knowledge/` directory + `INDEX.json` writer helper
4. **Custom code directory** — Create `custom/` directory
5. **Agent exploration tools** — Document which exec commands are safe for exploration
6. **Agent implementation flow** — Code writing pattern (write → test → report → iterate)
7. **Feedback mechanism** — `requires_feedback` field + app-side handling
8. **Progress announcements** — Update TaskWatcher for longer tasks
9. **Testing** — Walk through 3-4 explore + implement cycles
