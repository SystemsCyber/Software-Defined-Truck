#ifndef SSSF_H_
#define SSSF_H_

#include <Arduino.h>
#include <SensorNode/SensorNode.h>
#include <HTTP/HTTPClient.h>
#include <NetworkStats/NetworkStats.h>
#include <TimeClient/TimeClient.h>
#include <EthernetUdp.h>
#include <ArduinoJson.h>
#include <IPAddress.h>
#include <FlexCAN_T4.h>

class SSSF: private SensorNode, private HTTPClient
{
private:
    uint32_t id;
    uint32_t index;
    uint32_t frameNumber;
    TimeClient timeClient;

    NetworkStats *networkHealth;

    int comBlockSize = 0;
    int comHeadSize = 0;

    unsigned int sendInterval = 12;
    unsigned int lastSend = 0;

public:
    struct COMMBlock
    {
        uint32_t index;
        uint32_t frameNumber;
        uint64_t timestamp;
        uint8_t type;
        union
        {
            struct WSensorBlock sensorFrame;
            struct WCANBlock canFrame;
            NetworkStats::NodeReport *healthReport;
        };
    };

    SSSF(const char* serverAddress, DynamicJsonDocument& _attachedDevice, uint32_t _can0Baudrate);
    SSSF(String& serverAddress, DynamicJsonDocument& _attachedDevice, uint32_t _can0Baudrate);
    SSSF(IPAddress& serverAddress, DynamicJsonDocument& _attachedDevice, uint32_t _can0Baudrate);

    SSSF(const char* serverAddress, DynamicJsonDocument& _attachedDevice, uint32_t _can0Baudrate, uint32_t can1Baudrate);
    SSSF(String& serverAddress, DynamicJsonDocument& _attachedDevice, uint32_t _can0Baudrate, uint32_t can1Baudrate);
    SSSF(IPAddress& serverAddress, DynamicJsonDocument& _attachedDevice, uint32_t _can0Baudrate, uint32_t can1Baudrate);

    virtual bool setup();
    virtual void forwardingLoop(bool print = false);

private:
    void write(struct CAN_message_t &canFrame);
    void write(struct CANFD_message_t &canFrame);
    void write(NetworkStats::NodeReport *healthReport);

    int readCOMMBlock(struct COMMBlock *buffer);

    void pollServer();
    void pollCANNetwork(struct CAN_message_t &canFrame);

    void start(struct Request *request);
    void stop();

    String dumpCOMMBlock(struct COMMBlock &commBlock);
};

#endif /* SSSF_H_ */