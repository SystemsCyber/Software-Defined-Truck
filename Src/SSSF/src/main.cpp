#include <Arduino.h>
#include <SSSF/SSSF.h>
#include <Configuration/Load.h>
#include <FlexCAN_T4.h>

Load config;
SSSF *sssf;

void setup() {
    // Open serial communications and wait for port to open:
    Serial.begin(9600);
    while (!Serial) {
        // Proceed after 5 seconds even if theres no serial connection
        if (millis() > (uint32_t) 5000) {
            break;
        }
    }
    config.init();
    sssf = new SSSF(config.config["attachedDevices"], 250000);
    sssf->setup();
}

void loop() {
    sssf->forwardingLoop();
}