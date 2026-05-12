# Camera Person Follower — Exploration Notes

## Capabilities
- MIPI CSI camera at /dev/video0
- OpenCV 4.10.0, no ML frameworks
- Available: background subtraction (MOG2), color tracking (HSV), contour detection

## Approach Chosen
**Background subtraction** via cv2.createBackgroundSubtractorMOG2()
- No training data needed
- Real-time, low CPU
- Works with any moving object (not just people)
- Falls back to stopping when target lost

## Method 2 (Alternative)
HSV color tracking — calibrate to warm/skin tones. Works when person is
the only warm-colored object. More stable than MOG2 in good lighting.

## Limitations
- No person classification (can detect ANY moving object, not just people)
- Sensitive to lighting changes (MOG2 adapts slowly)
- Camera angle cannot tilt — only horizontal tracking
- No ML = no face detection, no pose estimation
