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

    union WCANFrame  //TODO: Deconstructor? It doesn't envoke dynamic memory so not sure.
    {
        struct CAN_message_t can;
        struct CANFD_message_t canFD;

        WCANFrame() { memset(this, 0, sizeof(WCANFrame));};
        ~WCANFrame() = default;
        WCANFrame(struct CAN_message_t *_can): can(*_can) {};
        WCANFrame(struct CAN_message_t _can): can(_can) {};
        WCANFrame(struct CANFD_message_t *_canFD): canFD(*_canFD) {};
        WCANFrame(struct CANFD_message_t _canFD): canFD(_canFD) {};
        WCANFrame(union WCANFrame *frame) {memcpy(this, &frame, sizeof(WCANFrame));};
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
            p.printf("Sequence Number: %d Timestamp: %d Need Response: %d\n", sequenceNumber, timestamp, needResponse);
            if (fd)
            {
                struct CANFD_message_t f = frame.canFD;
                p.printf("CAN ID: %d CAN Timestamp: %d\n", f.id, f.timestamp);
                p.printf("Length: %d Data: ", f.len);
                p.write(f.buf, size_t(f.len));
            }
            else
            {
                struct CAN_message_t f = frame.can;
                p.printf("CAN ID: %d CAN Timestamp: %d\n", f.id, f.timestamp);
                p.printf("Length: %d Data: ", f.len);
                p.write(f.buf, size_t(f.len));
            }
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
};

#endif /* CANNode_h_ */