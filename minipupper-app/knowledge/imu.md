# IMU (Inertial Measurement Unit)

## Hardware
- Onboard IMU connected via ESP32 co-processor
- Access via: `MangDang.mini_pupper.ESP32Interface`
- Data: accelerometer (ax, ay, az in Gs) + gyroscope (gx, gy, gz in deg/s)

## API
```python
from MangDang.mini_pupper.ESP32Interface import ESP32Interface
esp32 = ESP32Interface()
data = esp32.imu_get_data()
# Returns: {'ax': 0.05, 'ay': 0.08, 'az': -1.06, 'gx': 7.9, 'gy': 2.4, 'gz': -0.6}
```

## Update Rate
- 20 Hz (0.05s between reads)
