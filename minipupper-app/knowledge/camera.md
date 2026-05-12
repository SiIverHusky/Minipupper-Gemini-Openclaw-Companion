# Camera Capabilities

## Hardware
- Device: /dev/video0 (MIPI CSI camera, connected via ribbon cable to CSI port)
- Resolution: tested at 640x480 (via OpenCV default capture)
- Raspberry Pi detects camera: `vcgencmd get_camera` returns `supported=1 detected=1`
- Works with standard Video4Linux2 driver stack

## Software Stack
- OpenCV 4.10.0 — full capture: read frames, process, display
- PIL 10.4.0 — image manipulation, resize for ST7789 LCD
- numpy 1.26.4 — array operations
- scipy — available
- sklearn — available
- **Not available:** torch, tensorflow, tflite, face_recognition, picamera, picamera2

## What's Possible (no ML libraries needed)
- ✅ Photo capture → display on LCD (working: capture_and_show.py)
- ✅ Motion detection (frame differencing with OpenCV)
- ✅ Color tracking (HSV thresholding + centroid)
- ✅ Edge detection (Canny)
- ✅ Background subtraction (MOG2)

## What's Possible (with scipy/sklearn)
- HOG + SVM person detection (sliding window, CPU-only, slow)
- Background subtraction + contour analysis
- Simple object tracking (CentroidTracker)

## What's NOT Possible (without installing ML frameworks)
- ❌ Face recognition/detection (no face_recognition, no dlib)
- ❌ Deep learning object detection (no YOLO, no SSD, no tensorflow)
- ❌ Neural network inference (no torch, no tflite)

## Key Scripts
- `scripts/capture_and_show.py` — capture photo + display on ST7789 LCD
  Usage: `python3 scripts/capture_and_show.py`
