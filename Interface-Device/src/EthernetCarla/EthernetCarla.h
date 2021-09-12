#ifndef ethernet_carla_h_
#define ethernet_carla_h_

#include <Arduino.h>
#include <EthernetUdp.h>
#include <HTTPClient/HTTPClient.h>
#include <IPAddress.h>

#define CARLA_PACKET_SIZE 20

class EthernetCarla
{
private:
    HTTPClient server;
    EthernetUDP carla;      // Multicast socket to receive CARLA frames from.
    EthernetUDP can;        // Multicast socket to send CAN frames on.

    IPAddress mcastIP;
    int carlaPort;
    int canPort;

public:
    uint8_t _rxBuffer[CARLA_PACKET_SIZE];   // Buffer to hold incoming carla messages.

    struct CARLA_UDP // CARLA frame information struct
    {
        uint32_t frameNumber;
        float throttle, steer, brake;
        bool handBrake, reverse, manualGearShift;
        uint8_t gear;
    } _frame;

    EthernetCarla() = default;
    // Returns 1 if successful, 0 otherwise.
    int init();
    // Begin monitoring all interfaces for activity and respond appropriately.
    // Returns the number of bytes read, or 0 if none are available.
    int monitor(bool verbose = false);
    // Read a single message from the carla socket.
    // Returns the number of bytes read, or 0 if none are available.
    int read(bool verbose = false);
    // Write size bytes from buffer into the packet.
    // Returns 1 if the packet was sent successfully, 0 if there was an error.
    int write(const char *txBuffer, int size);
    // Write size_t bytes from buffer into the packet.
    // Returns 1 if the packet was sent successfully, 0 if there was an error.
    int write(const char *txBuffer, size_t size);
    // Dumps the packet information to serial.
    static void dumpPacket(uint8_t *buffer, int packetSize, IPAddress remoteIP); 
    // Dumps the frame information to serial.
    static void dumpFrame(CARLA_UDP frame);

private:
    void unsuccessfulRegistration();
    void do_POST();
    void do_DELETE();

    IPAddress parseIPAddress(String IP);
};

#endif /* ethernet_carla_h_ */