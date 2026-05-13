# Camera Live Video Feed

## Overview
Live video feed from the Mini Pupper MIPI CSI camera displayed on the ST7789 LCD (320x240).

## Hardware
- **Camera:** /dev/video0, MIPI CSI, 640x480 @ 30 FPS via OpenCV
- **Display:** ST7789 SPI-based 320x240 LCD (via MangDang.mini_pupper.display.Display)
- **Available video nodes:** /dev/video0, /dev/video10-video23 (kernel driver metadata nodes)

## Approach for Live Feed

### Simple Blocking Loop


### Threaded Approach (Recommended)
Use a producer (camera thread) and consumer (display in main loop or timer).



## Performance Notes
- SPI bus limits display updates to ~10-15 FPS
- OpenCV capture at 30 FPS, bottleneck is SPI write
- CPU usage: ~30-50%% on Pi 4
- Works on Raspberry Pi 4B (the Mini Pupper brain)

## Display Module Details
- MangDang.mini_pupper.display.Display() creates display instance
- disp.display(pil_image) - caller must resize to display resolution
- Uses ST7789 driver (MangDang.LCD.ST7789.ST7789)

## Limitations
- No hardware acceleration
- Best for short-duration interactions (10-30 seconds)
- SPI writes are blocking

## Existing Infrastructure
- scripts/capture_and_show.py - single capture + display
- No existing live-feed script
