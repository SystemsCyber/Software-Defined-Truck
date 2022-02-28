#ifndef CANNode_h_
#define CANNode_h_

#include <Arduino.h>
#include <EthernetUdp.h>
#include <IPAddress.h>
#include <ArduinoLog.h>
#include <FlexCAN_T4.h>

enum SessionStatus
{
    Inactive,
    Active
};

class CANNode
{
private:
    EthernetUDP canSock;
    IPAddress canIP;
    uint16_t canPort;

    int canBlockSize = 0;
    int canHeadSize = 0;
    
protected:
    int canSize = 0;
    int canFDSize = 0;

    uint32_t can0BaudRate = 0;
    uint32_t can1BaudRate = 0;
    FlexCAN_T4<CAN0, RX_SIZE_256, TX_SIZE_16> can0;
    FlexCAN_T4<CAN1, RX_SIZE_256, TX_SIZE_16> can1;

    uint8_t mac[6];  // Hostname is "WIZnet" + last three bytes of the MAC.
    uint32_t sequenceNumber = 1;
    volatile boolean sessionStatus;

public:
    struct WCANBlock
    {
        uint32_t sequenceNumber;
        bool needResponse;
        bool fd;
        union
        {
            struct CAN_message_t can;
            struct CANFD_message_t canFD;
        };
    };
    
    CANNode();
    CANNode(uint32_t _can0Baudrate);
    CANNode(uint32_t _can0Baudrate, uint32_t _can1Baudrate);
    virtual int init();
    virtual bool startSession(IPAddress _ip, uint16_t _port);
    virtual bool startSession(String _ip, uint16_t _port);
    virtual int parsePacket();
    virtual int read(uint8_t *buffer, size_t size);
    virtual int read(struct WCANBlock *buffer);
    virtual int beginPacket();
    virtual int beginPacket(struct WCANBlock &canBlock);
    virtual int write(const uint8_t *buffer, size_t size);
    virtual int write(struct WCANBlock *canFrame);
    virtual int endPacket(bool incrementSequenceNumber = true);
    virtual void stopSession();
    String dumpCANBlock(struct WCANBlock &canBlock);

private:
    void setupLogging();
    void setupCANChannels();
    static void checkHardware();
    static void checkLink();

    static void printPrefix(Print* _logOutput, int logLevel);
    static void printTimestamp(Print* _logOutput);
    static void printLogLevel(Print* _logOutput, int logLevel);
    static void printSuffix(Print* _logOutput, int logLevel);
};

#endif /* CANNode_h_ */