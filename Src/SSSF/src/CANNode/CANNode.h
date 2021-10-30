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

protected:
    uint8_t mac[6];  //MAC address of WIZnet Device. Hostname is "WIZnet" + last three bytes of the MAC.
    uint32_t sequenceNumber;
    volatile boolean sessionStatus;

public:

    union WCANFrame
    {
        struct CAN_message_t can;
        struct CANFD_message_t canFD;
    };

    struct WCANBlock: public Printable
    {
        uint32_t sequenceNumber;
        uint32_t timestamp;
        bool needResponse;
        bool fd;
        union WCANFrame frame;

        size_t printTo(Print &p) const
        {
            size_t s = 0;
            s += p.printf("Sequence Number: %d Timestamp: %d Need Response: %d\n", sequenceNumber, timestamp, needResponse);
            if (fd)
            {
                struct CANFD_message_t f = frame.canFD;
                s += p.printf("CAN ID: %d CAN Timestamp: %d\n", f.id, f.timestamp);
                s += p.printf("Length: %d Data: ", f.len);
                s += p.write(f.buf, size_t(f.len));
            }
            else
            {
                struct CAN_message_t f = frame.can;
                s += p.printf("CAN ID: %d CAN Timestamp: %d\n", f.id, f.timestamp);
                s += p.printf("Length: %d Data: ", f.len);
                s += p.write(f.buf, size_t(f.len));
            }
            return s;
        };
    };
    
    CANNode();
    virtual int init();
    virtual bool startSession(IPAddress _ip, uint16_t _port);
    virtual bool startSession(String _ip, uint16_t _port);
    virtual int read(uint8_t *buffer, size_t size);
    virtual int read(struct WCANBlock *buffer);
    virtual int beginPacket(struct WCANBlock *canBlock);
    virtual int write(const uint8_t *buffer, size_t size);
    virtual int write(struct WCANBlock *canFrame);
    virtual int endPacket();
    virtual void stopSession();

private:
    static void checkHardware();
    static void checkLink();

    static void printPrefix(Print* _logOutput, int logLevel);
    static void printTimestamp(Print* _logOutput);
    static void printLogLevel(Print* _logOutput, int logLevel);
    static void printSuffix(Print* _logOutput, int logLevel);
};

#endif /* CANNode_h_ */