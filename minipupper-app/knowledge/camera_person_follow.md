# Camera Person Follow Module

## Location
`custom/camera_person_follow/main.py`

## Purpose
Enables the Mini Pupper robot to visually track and follow a person using the onboard MIPI camera. No additional hardware or ML models required — uses OpenCV's built-in HOG + SVM people detector.

## How It Works

1. **Capture**: Grabs frames from `/dev/video0` at 640x480
2. **Detect**: Downscales to 320x240 and runs OpenCV HOG people detector
3. **Select**: Picks the largest person bounding box (closest person)
4. **Control Loop (20 Hz)**:
   - Computes lateral offset from center → PID → `lx` (steering)
   - Person height ratio vs target → proportional → `ly` (forward/back)
5. **Robot Interface**: Sends velocity commands via UDP Joystick protocol (port 8830)

## Dependencies
- OpenCV 4.x (with `cv2.HOGDescriptor`)
- NumPy
- `UDPComms` (from `~/apps-md-robots/api/`)
- Robot services: `joystick.service` + `robot.service`

## Usage
```bash
cd ~/minipupper-app
python3 custom/camera_person_follow/main.py
```

### Options
| Flag | Default | Description |
|------|---------|-------------|
| `--debug` | off | Save annotated frames to /tmp/person_follow/ |
| `--max-speed` | 0.35 | Max forward/back velocity (0-1) |
| `--steer-gain` | 1.2 | PID proportional gain for steering |
| `--follow-distance` | 0.35 | Target person height ratio in frame |
| `--lost-frames` | 30 | Frames without detection before stop |

## Control Parameters
- **Steering**: PID controller (KP=1.2, KI=0.5, KD=0.3) on horizontal offset
- **Speed**: Proportional to distance error, clamped to `--max-speed`
- **Lost behavior**: Stops after 30 missed frames, exits after 60

## Limitations
- HOG detector won't detect from behind or at extreme angles
- Works best with a full/partial frontal view of a person standing
- No depth sensing — uses apparent size as distance proxy
- Performance: ~20 FPS on RPi overclocked, may drop with multiple detections

## Future Improvements
- Add TensorFlow Lite person detection model for better accuracy
- Implement Kalman filter for smooth tracking
- Add obstacle avoidance (ultrasonic sensor)
- Store person appearance features for re-identification
