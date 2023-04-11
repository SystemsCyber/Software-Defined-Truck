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

IPAddress ip(192,168,1,23);

void setup() {
    // Open serial communications and wait for port to open:
    Serial.begin(115200);
    while (!Serial) {
        // Proceed after 30 seconds even if theres no serial connection
        if (millis() > (uint32_t) 30000) {
            break;
        }
    }

    config.init();
    // sssf = new SSSF("LAPTOP-A89GD15G.local", config.config, 250000);
    sssf = new SSSF(ip, config.config, 0);
    sssf->setup();
}

void loop() {
    // sssf->forwardingLoop(true);
    sssf->forwardingLoop(false);
}

// TimeClient* timeClient;
// uint8_t mac[6];

// unsigned int printInterval = 1000;
// unsigned int lastPrint = 0;
// CAN_message_t canFrame;

// void setup()
// {
	// CORE_PIN3_CONFIG = PORT_PCR_MUX(2);
	// // CORE_PIN4_CONFIG = PORT_PCR_MUX(2);
	// pinMode(2, OUTPUT);
	// pinMode(35, OUTPUT);

	// digitalWrite(2, HIGH);
	// digitalWrite(35, HIGH);
	// pinMode(14, OUTPUT); digitalWrite(14, LOW); /* optional tranceiver enable pin */
  	// pinMode(35, OUTPUT); digitalWrite(35, LOW); /* optional tranceiver enable pin */
    // teensyMAC(mac);
    // Ethernet.begin(mac);
    // Serial.begin(9600);
    // while (!Serial) {
        // Proceed after 10 seconds even if theres no serial connection
    //     if (millis() > (uint32_t) 10000) {
    //         break;
    //     }
    // }
	// Serial.println("got to here");

	// can0.begin();
	// can0.setBaudRate(250000);
	// can0.setMaxMB(16);
  	// can0.enableFIFO();
	// can0.setTX();
	// can0.setRX();
	// Serial.println("CAN0 mailbox Status:");
  	// can0.mailboxStatus();
    // Log.begin(LOG_LEVEL_VERBOSE, &Serial);
    // timeClient = new TimeClient(&Log);
    // timeClient->setup();
    // timeClient->session = true;
// }

// void loop()
// {
	// Serial.println("ere");
	// struct CAN_message_t canFrame;
	// if (can0.read(canFrame))
	// {
	//     Serial.print("ID: ");
	//     Serial.print(canFrame.id, HEX);
	//     Serial.print(" LEN: ");
	//     Serial.print(canFrame.len);
	//     Serial.print(" DATA: ");
	//     for (int i = 0; i < canFrame.len; i++)
	//     {
	//         Serial.print(canFrame.buf[i], HEX);
	//         Serial.print(" ");
	//     }
	//     Serial.println();
	// }
	// if ( can0.read(canFrame) ) {
    // 	can0.write(canFrame);
  	// }
	// while (true)
	// {
	// 	if (millis() - lastPrint >= printInterval)
	// 	{
	// 		lastPrint = millis();
	// 		// canFrame.mb = 0;
	// 		canFrame.id = 0x18F00411;
	// 		canFrame.len = 1;
	// 		canFrame.flags.extended = true;
	// 		canFrame.buf[0] = 0xFF;
	// 		Serial.println(can0.write(canFrame));
	// 		// Serial.println(lastPrint);
	// 	}
	// }
	// Serial.println("here");
    // timeClient->update();
    // if (millis() - lastPrint >= printInterval)
    // {
    //     lastPrint = millis();
    //     Serial.print("Timestamp: ");
    //     Serial.println(timeClient->getEpochTimeUS());
    // }
// }