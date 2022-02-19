#include <Arduino.h>
#include <SSSF/SSSF.h>
#include <Configuration/Load.h>
#include <FlexCAN_T4.h>
#include <IPAddress.h>
#include <ArduinoLog.h>
#include <TimeClient/TimeClient.h>
#include <TeensyID.h>

Load config;
SSSF *sssf;

IPAddress ip(192,168,1,47);

void setup() {
    // Open serial communications and wait for port to open:
    Serial.begin(9600);
    while (!Serial) {
        // Proceed after 10 seconds even if theres no serial connection
        if (millis() > (uint32_t) 10000) {
            break;
        }
    }
    config.init();
    // sssf = new SSSF("LAPTOP-A89GD15G", config.config, 250000);
    sssf = new SSSF(ip, config.config, 250000);
    sssf->setup();
}

void loop() {
    sssf->forwardingLoop();
}

// TimeClient* timeClient;
// uint8_t mac[6];

// unsigned int printInterval = 1000;
// unsigned int lastPrint = 0;

// void setup()
// {
//     teensyMAC(mac);
//     Ethernet.begin(mac);
//     Serial.begin(9600);
//     while (!Serial) {
//         // Proceed after 10 seconds even if theres no serial connection
//         if (millis() > (uint32_t) 10000) {
//             break;
//         }
//     }

//     Log.begin(LOG_LEVEL_VERBOSE, &Serial);
//     timeClient = new TimeClient(&Log);
//     timeClient->setup();
// }

// void loop()
// {
//     timeClient->update();
//     // if (millis() - lastPrint >= printInterval)
//     // {
//     //     lastPrint = millis();
//     //     Serial.print("Timestamp: ");
//     //     Serial.println(timeClient->getEpochTimeUS());
//     // }
// }