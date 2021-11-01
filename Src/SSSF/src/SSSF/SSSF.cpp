#include <Arduino.h>
#include <SSSF/SSSF.h>
#include <SensorNode/SensorNode.h>
#include <HTTP/HTTPClient.h>
#include <NetworkStats/NetworkStats.h>
#include <EthernetUdp.h>
#include <ArduinoJson.h>
#include <TimeLib.h>
#include <NTPClient.h>
#include <Dns.h>
#include <FlexCAN_T4.h>

SSSF::SSSF(DynamicJsonDocument _attachedDevice, uint32_t _can0Baudrate):
    SensorNode(),
    HTTPClient(_attachedDevice, serverAddress),
    timeClient(ntpSock),
    can0BaudRate(_can0Baudrate)
    {}

SSSF::SSSF(DynamicJsonDocument _attachedDevice, uint32_t _can0Baudrate, uint32_t _can1Baudrate):
    SensorNode(),
    HTTPClient(_attachedDevice, serverAddress),
    timeClient(ntpSock),
    can0BaudRate(_can0Baudrate),
    can1BaudRate(_can1Baudrate)
    {}

bool SSSF::setup()
{
    if (init() && connect())
    {
        Log.noticeln("Setting up the Teensys Real Time Clock.");
        setupClock();
        setupCANChannels();
        return true;
    }
    return false;
}

void SSSF::forwardingLoop()
{
    pollClock();
    pollServer();
    if (sessionStatus == Active)
    {
        struct COMMBlock msg = {0};
        struct CAN_message_t canFrame;
        if (can0BaudRate && can0.read(canFrame)) write(&canFrame);
        if (can1BaudRate && can1.read(canFrame)) write(&canFrame);
        int packetSize = CANNode::read(reinterpret_cast<uint8_t*>(&msg), sizeof(struct COMMBlock));
        if (packetSize)
        {
            if (msg.type == 1)
            {
                //adding 28 for UDP header
                networkHealth->update(msg.id, packetSize + 28, msg.timestamp, msg.canFrame.sequenceNumber);
                can0.write(msg.canFrame.frame.can);
                if (can1BaudRate) can1.write(msg.canFrame.frame.can);
            }
            else if (msg.type == 2)
            {
                networkHealth->update(msg.id, packetSize + 28, msg.timestamp, msg.frameNumber);
                frameNumber = msg.frameNumber;
            }
            else if (msg.type == 3) write(networkHealth->HealthReport);
        }
    }
}

void SSSF::write(struct CAN_message_t *canFrame)
{
    struct COMMBlock msg = {0};
    msg.id = id;
    msg.frameNumber = frameNumber;
    msg.timestamp = millis();
    msg.type = 1;
    CANNode::beginPacket(msg.canFrame);
    msg.canFrame.fd = false;
    msg.canFrame.needResponse = false;
    memcpy(&msg.canFrame.frame, canFrame, sizeof(CAN_message_t));
    CANNode::write(reinterpret_cast<uint8_t*>(&msg), sizeof(struct COMMBlock));
    CANNode::endPacket();
}

void SSSF::write(struct CANFD_message_t *canFrame)
{
    struct COMMBlock msg = {0};
    msg.id = id;
    msg.frameNumber = frameNumber;
    msg.timestamp = millis();
    msg.type = 1;
    CANNode::beginPacket(msg.canFrame);
    msg.canFrame.fd = true;
    msg.canFrame.needResponse = false;
    memcpy(&msg.canFrame.frame, canFrame, sizeof(CANFD_message_t));
    CANNode::write(reinterpret_cast<uint8_t*>(&msg), sizeof(struct COMMBlock));
    CANNode::endPacket();
}

void SSSF::write(NetworkStats::NodeReport *healthReport)
{
    struct COMMBlock msg = {0};
    msg.id = id;
    msg.frameNumber = frameNumber;
    msg.timestamp = millis();
    msg.type = 4;
    CANNode::beginPacket();
    size_t baseCOMMBlockSize = sizeof(COMMBlock::id) + 
                                sizeof(COMMBlock::frameNumber) +
                                sizeof(COMMBlock::timestamp) + 
                                sizeof(COMMBlock::type);
    uint8_t report[baseCOMMBlockSize + networkHealth->size];
    memcpy(&msg, report, baseCOMMBlockSize);
    memcpy(healthReport, report + baseCOMMBlockSize, networkHealth->size);
    CANNode::write(report, baseCOMMBlockSize + networkHealth->size);
    CANNode::endPacket(false);
}

void SSSF::setupClock()
{
    timeClient.begin();
    setSyncProvider(getExternalTime(Teensy3Clock.get()));
    setSyncInterval(1);
}

void SSSF::setupCANChannels()
{
    Log.noticeln("Setting up can0 with a bitrate of %d", can0BaudRate);
    can0.begin();
    can0.setBaudRate(can0BaudRate);
    if (can1BaudRate)
    {
        Log.noticeln("Setting up can1 with a bitrate of %d", can1BaudRate);
        can1.begin();
        can1.setBaudRate(can1BaudRate);
    }
}

void SSSF::pollClock()
{
    now();
    if (timeClient.update())
    {
        Teensy3Clock.set(timeClient.getEpochTime());
        setTime(timeClient.getEpochTime());
        Ethernet.maintain(); //Only tries to renew if 3/4 through lease
    }
}

void SSSF::pollServer()
{
    struct Request request;
    if(HTTPClient::read(&request))
    {
        if (request.method.equalsIgnoreCase("POST"))
        {
            start(&request);
        }
        else if (request.method.equalsIgnoreCase("DELETE"))
        {
            id = 0;
            frameNumber = 0;
            stop();
        }
        else
        {
            struct Response notImplemented = {501, "NOT IMPLEMENTED"};
            HTTPClient::write(&notImplemented);
        }
    }
}

void SSSF::start(struct Request *request)
{
    id = request->json["ID"];
    size_t membersSize = request->json["MEMBERS"].size();
    members = new uint16_t [membersSize];
    for (size_t i = 0; i < membersSize; i++)
    {
        members[i] = request->json["MEMBERS"][i].as<uint16_t>();
    }
    frameNumber = 0;
    networkHealth = new NetworkStats(id, members, membersSize);
    String ip = request->json["IP"];
    if (CANNode::startSession(ip, request->json["PORT"]))
    {
        Log.noticeln("\tID: %d", id);
    }
}

void SSSF::stop()
{
    id = 0;
    delete &members;
    delete &networkHealth;
    CANNode::stopSession();
}