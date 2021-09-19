#include <Arduino.h>
#include <Carla/Carla.h>
#include <FlexCAN_T4.h>

Carla carla;
FlexCAN_T4<CAN0, RX_SIZE_256, TX_SIZE_16> can0;
FlexCAN_T4<CAN1, RX_SIZE_256, TX_SIZE_16> can1;
CAN_message_t msg;
size_t canSize = sizeof(msg);

void setup() {
    // Open serial communications and wait for port to open:
    Serial.begin(9600);
    while (!Serial) {
        // Proceed after 5 seconds even if theres no serial connection
        if (millis() > (uint32_t) 5000) {
            break;
        }
    }
    can0.begin();
    can0.setBaudRate(500000);
    can1.begin();
    can1.setBaudRate(500000);
    carla.init();
}

void loop() {
    carla.monitor();
    if (can0.read(msg))
    {
        uint8_t canFrameBuffer[canSize];
        memcpy(&canFrameBuffer, &msg, canSize);
        carla.write(canFrameBuffer, canSize);
    }
    if (can1.read(msg))
    {
        uint8_t canFrameBuffer[canSize];
        memcpy(&canFrameBuffer, &msg, canSize);
        carla.write(canFrameBuffer, canSize);
    }
}