# Motors / Servos

## Control
- 12 servos (3 per leg × 4 legs)
- Controlled via ESP32 co-processor
- API: `ESP32Interface.servos_set_position(channel, angle)`, `servos_get_position()`, `servos_get_load()`
- High-level movement via `minipupper_control.py`

## API
```python
from MangDang.mini_pupper.ESP32Interface import ESP32Interface
esp32 = ESP32Interface()
# Read servo positions
positions = esp32.servos_get_position()
# Read servo loads (torque)
loads = esp32.servos_get_load()
# Set servo position
esp32.servos_set_position(channel=0, position=90)
```
