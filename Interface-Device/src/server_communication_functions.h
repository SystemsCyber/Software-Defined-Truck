#include <Ethernet.h>
#include <EthernetUdp.h>

// buffers for receiving and sending data
char packetBuffer[UDP_TX_PACKET_MAX_SIZE];  // buffer to hold incoming packet,
char ReplyBuffer[] = "acknowledged";        // a string to send back

void init_UDP_connection(byte mac[6], unsigned int localPort, IPAddress remoteip){
if (Ethernet.begin(mac) == 0) {

    Serial.println("Failed to configure Ethernet using DHCP");

    if (Ethernet.hardwareStatus() == EthernetNoHardware) {

      Serial.println("Ethernet shield was not found.  Sorry, can't run without hardware. :(");

    } else if (Ethernet.linkStatus() == LinkOFF) {

      Serial.println("Ethernet cable is not connected.");

    }
  }

  Serial.print("Obtained IP: "); Serial.println(Ethernet.localIP());

  
  // start UDP
  Udp.begin(localPort);
 
}

void UDP_send_CAN(int channel, int channel_index, UDP_CAN_Package) {
    Serial.println("Sending CAN Frame over UDP: Unfinished");

}

int UDP_receive_CAN() {
    Serial.println("Receiving CAN Frame over UDP: Unfinished");
    return 1;
}

struct UDP_CAN_Package{
    int index;
    char arb_ID[4];
    int dlc;
    int data[8];
}