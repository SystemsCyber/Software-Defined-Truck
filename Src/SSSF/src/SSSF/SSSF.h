#ifndef SSSF_H_
#define SSSF_H_

#include <Arduino.h>
#include <SensorNode/SensorNode.h>
#include <HTTP/HTTPClient.h>
#include <NetworkStats/NetworkStats.h>
// #include <TimeClient/TimeClient.h>
#include <PTPClient/PTPClient.h>
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
    PTPClient ptpClient;
    uint64_t msgReceivedTime = 0;
    
    NetworkStats *networkHealth;

    int comPackedHeadSize = 14;
    int reportSize = 0;
    int comPackedMaxSize = 90u;

    // For Testing
    unsigned int sendInterval = 30;
    unsigned int lastSend = 0;
    // -----------
    uint8_t *msgBuffer = nullptr;

public:
    struct COMMBlock
    {
        uint8_t index;
        uint8_t type;
        uint32_t frameNumber;
        uint64_t timestamp;
        union
        {
            struct WSensorBlock sensorFrame;
            struct WCANBlock canFrame;
            NetworkStats::NodeReport *healthReport;
            uint64_t timeFrame;
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

    void write(struct CAN_message &canFrame);
private:
    void write(struct CANFD_message &canFrame);
    void write(NetworkStats::NodeReport *healthReport);

    size_t packCOMMBlock(struct COMMBlock &commBlock);
    int read();
    int unpackCOMMBlock();

    void sendDelayReq();

    void pollServer();
    void pollCANNetwork();

    void start(struct Request *request);
    void stop();

    String dumpCOMMBlock(struct COMMBlock &commBlock);
};

#endif /* SSSF_H_ */