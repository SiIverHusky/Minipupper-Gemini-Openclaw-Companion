# Test Results

## Camera Test (2026-05-12)
- Camera: OK at 640x480
- Imports: all resolved (cv2, numpy, UDPComms)
- Robot services: running (joystick, run_robot, web-controller)
- Test image: /tmp/follower_test.jpg

## Full Follow Test
- `python3 custom/camera_person_follower.py --duration 30 --preview`
- Requires a person visible in the camera frame
- Robot will rotate to face the tracked person
- Will move forward/backward to maintain distance

## Known Issues
- MOG2 background model takes ~1-2s to initialize
- Target may be lost if person stops moving for >5s
- Bright backgrounds may wash out contours
