#include <Arduino.h>
// #include <Ethernet.h>
// #include <EthernetUdp.h>
#include <EthernetCarla/EthernetCarla.h>

//By default it picks up an IP from the DHCP server, its hostname is generated automatically as 
// the "WIZnet" + last three bytes of the MAC, (e.g. EFFEED in our case ) - so in total WiZnetEFFEED
// byte mac[] = {
//     0xDE, 0xAD, 0xBE, 0xEF, 0xFE, 0xED
// };

// char packetBuffer[UDP_TX_PACKET_MAX_SIZE];  //Buffer to hold incoming packet

// char replyBuffer[64];                       //Buffer to hold outgoing packet


EthernetCarla carla("/config.txt");
// EthernetUDP udp;

void setup() {

    // Open serial communications and wait for port to open:
    Serial.begin(9600);
    while (!Serial) {
        // Proceed after 5 seconds even if theres no serial connection
        if (millis() > (uint32_t) 5000) {
            break;
        }
        //;
    }

    carla.init();
    // IPAddress mip(224,1,1,1);
    // Ethernet.begin(mac);
    // udp.beginMulticast(mip, 5007);
}

void loop() {
    if (carla.monitor())
    {
        carla.write(reinterpret_cast<char *>(carla._rxBuffer), CARLA_PACKET_SIZE);
    }
    // if(udp.parsePacket())
    // {
    //     udp.read(packetBuffer, UDP_TX_PACKET_MAX_SIZE);
    //     Serial.println(packetBuffer);
    // }
}


/*
  Processing sketch to run with this example
 =====================================================

 // Processing UDP example to send and receive string data from Arduino
 // press any key to send the "Hello Arduino" message


 import hypermedia.net.*;

 UDP udp;  // define the UDP object


 void setup() {
 udp = new UDP( this, 6000 );  // create a new datagram connection on port 6000
 //udp.log( true );     // <-- printout the connection activity
 udp.listen( true );           // and wait for incoming message
 }

 void draw()
 {
 }

 void keyPressed() {
 String ip       = "192.168.1.177"; // the remote IP address
 int port        = 8888;    // the destination port

 udp.send("Hello World", ip, port );   // the message to send

 }

 void receive( byte[] data ) {      // <-- default handler
 //void receive( byte[] data, String ip, int port ) { // <-- extended handler

 for(int i=0; i < data.length; i++)
 print(char(data[i]));
 println();
 }
 */
