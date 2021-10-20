#ifndef ethernet_carla_h_
#define ethernet_carla_h_

#include <Arduino.h>
#include <EthernetUdp.h>
#include <HTTPClient/HTTPClient.h>
#include <IPAddress.h>
#include <FlexCAN_T4.h>

#define CAN_message_t_size (size_t) 24
#define CAN_TX_BUFFER_SIZE (size_t) 36

class Carla
{
private:
    HTTPClient server;
    EthernetUDP carla;      // Multicast socket to receive CARLA frames from.
    EthernetUDP can;        // Multicast socket to send CAN frames on.

public:
    IPAddress mcastIP;
    int carlaPort;
    int canPort;

    struct CARLA_UDP // CARLA frame information struct
    {
        uint32_t frameNumber;
        float throttle, steer, brake;
        bool handBrake, reverse, manualGearShift;
        uint8_t gear;
    } _frame;
    uint32_t id;
    uint32_t sequenceNumber;
    uint8_t txCanFrameBuffer[CAN_TX_BUFFER_SIZE];

    Carla() = default;
    // Returns 1 if successful, 0 otherwise.
    int init();
    // Begin monitoring all interfaces for activity and respond appropriately.
    // Returns the number of bytes read, or 0 if none are available.
    int monitor(bool verbose = false);
    // Read a single message from the carla socket.
    // Returns the number of bytes read, or 0 if none are available.
    int read(bool verbose = false);
    // Write size_t bytes from buffer into the packet.
    // Returns 1 if the packet was sent successfully, 0 if there was an error.
    int write(const uint8_t *txBuffer, size_t size);
    // Write size_t bytes from buffer into the packet.
    // Returns 1 if the packet was sent successfully, 0 if there was an error.
    int write(const CAN_message_t *txBuffer);
    // Dumps the packet information to serial.
    static void dumpPacket(uint8_t *buffer, int packetSize, IPAddress remoteIP); 
    // Dumps the frame information to serial.
    static void dumpFrame(CARLA_UDP frame);

private:
    void do_POST(struct HTTPClient::Request sse);
    void do_DELETE();
};

#endif /* ethernet_carla_h_ */