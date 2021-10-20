#include <Arduino.h>
#include <Ethernet.h>
#include <EthernetUdp.h>

#define WIZNET_CHIP_SELECT 10
#define buffer_size 1

struct WCANFrame
{
    uint32_t id;
    uint64_t data;
    uint8_t dlc;
};

struct WCANBlock
{
    WCANFrame canframes[buffer_size];
};

struct WSenseBlock
{
    uint8_t num_signals;
    float* signals; //heap allocate this using num_signals and then fill it up
};

struct COMMBLOCK {
  uint8_t type; // set accordingly
  uint64_t frame_number;
  union {
    struct WCANFrame c;
    struct WSenseBlock s;
  } data; // access with some_info_object.data.a or some_info_object.data.b
}commblock;

EthernetUDP Udp;
uint8_t mac[] = {0xDE, 0xAD, 0xBE, 0xEF, 0xFE, 0xED};
unsigned int localPort = 8888;  
void init_udp(){
    Ethernet.init(WIZNET_CHIP_SELECT);
    IPAddress ip(192, 168, 1, 177);
    Ethernet.begin(mac, ip);
    Serial.begin(9600);
    while (!Serial) {
        ; // wait for serial port to connect. Needed for native USB port only
    }
    if (Ethernet.hardwareStatus() == EthernetNoHardware) {
        Serial.println("Ethernet shield was not found.  Sorry, can't run without hardware. :(");
        while (true) {
        delay(1); // do nothing, no point running without Ethernet hardware
        }
    }
    if (Ethernet.linkStatus() == LinkOFF) {
        Serial.println("Ethernet cable is not connected.");
    }

    // start UDP
    Udp.begin(localPort);
}

void init_multicast_udp(){
    int packetSize = Udp.parsePacket();
    if (packetSize) {
        Serial.print("Received packet of size ");
        Serial.println(packetSize);
        Serial.print("From ");
        IPAddress remote = Udp.remoteIP();
        for (int i=0; i < 4; i++) {
        Serial.print(remote[i], DEC);
        if (i < 3) {
            Serial.print(".");
        }
        }
        Serial.print(", port ");
        Serial.println(Udp.remotePort());

        Udp.beginPacket(Udp.remoteIP(), Udp.remotePort());
        Udp.write("Thanks");
        Udp.endPacket();
    }

}

void read_udp_packet(){

}