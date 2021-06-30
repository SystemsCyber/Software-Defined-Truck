#ifndef ethernet_carla_h_
#define ethernet_carla_h_

#include <Arduino.h>
#include <Ethernet.h>
#include <EthernetUdp.h>
#include <Configuration/LoadConfiguration.h>
#include <vector>

#define CARLA_PACKET_SIZE 20
#define SETUP_PACKET_SIZE 16

class EthernetCarla
{
private:
    struct MCAST_SETUP
    {
        uint8_t mcastIP[4]; // IPv4 multicast address
        int carlaPort;
        int canPort;
    } _mcast;
    IPAddress mcastIP;
    const char *_filename;
    LoadConfiguration _config;
    unsigned long _lastHeartbeat = 0;
    const unsigned long _heartbeatInterval = 60 * 1000;
public:
    uint8_t _rxBuffer[CARLA_PACKET_SIZE];   // Buffer to hold incoming carla messages.
    uint8_t setupBuffer[SETUP_PACKET_SIZE]; // Buffer to hold incoming setup messages.
    EthernetClient _controller;          // Controller currently connected to the server.
    EthernetUDP _heartbeat;              // UDP socket for directly connecting to CARLA client.
    EthernetUDP _carla;                  // UDP Multicast socket to receive CARLA frames from.
    EthernetUDP _can;                    // UDP Multicast socket to send CAN frames on.
    bool newCommand = false;

    struct CARLA_UDP // CARLA frame information struct
    {
        uint32_t frameNumber;
        float throttle, steer, brake;
        bool handBrake, reverse, manualGearShift;
        uint8_t gear;
    } _frame;

    EthernetCarla() : EthernetCarla("/config.txt") {}
    EthernetCarla(const char *filename) : _filename(filename) {}
    // Initialize using the parameters provided via the SD Card.
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
    // Initialise the Ethernet shield to use the provided MAC address and
    // gain the rest of the configuration through DHCP.
    // Returns 0 if the DHCP configuration failed, and 1 if it succeeded.
    int ethernetBegin(int success);
    static void checkHardware();
    static void checkLink();
    // Send configuration info to the server. If the connection to the server
    // fails, retry every minute and print the time to show that the program is
    // still running.
    // Returns once it has successfully send the data to the server.
    void registerWithServer();
    bool sendConfig(unsigned long *lastAttempt);
    // Check for new connections and/or new packets.
    // If there are new setup instructions then update the class settings.
    bool checkForCommand();
    void startDataOperations();
    void stopDataOperations();

    void heartbeat();
    void discardPacket(EthernetClient &newCommand, int commandSize);
};

#endif /* ethernet_carla_h_ */