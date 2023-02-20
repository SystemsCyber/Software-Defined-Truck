# SSSF
## LED Status Blink Patterns
Devices have two LEDs (LED1 and LED2), but colors are not always the same.

- LED1 and LED2 Alternating Blinking = Error State
- LED1 On Steady = Connected to server
- LED1 Slow Blink = Connection failed. Retrying every 60 seconds.
- LED2 Fast Blink = Reading CAN messages and in session.