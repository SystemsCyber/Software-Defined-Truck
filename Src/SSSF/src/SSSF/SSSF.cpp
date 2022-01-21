#include <Arduino.h>
#include <SSSF/SSSF.h>
#include <SensorNode/SensorNode.h>
#include <CANNode/CANNode.h>
#include <HTTP/HTTPClient.h>
#include <NetworkStats/NetworkStats.h>
#include <W_NTPClient/W_NTPClient.h>
#include <EthernetUdp.h>
#include <ArduinoJson.h>
#include <Dns.h>
#include <FlexCAN_T4.h>

SSSF::SSSF(const char* serverAddress, DynamicJsonDocument& _attachedDevice, uint32_t _can0Baudrate):
    CANNode(_can0Baudrate),
    SensorNode(),
    HTTPClient(_attachedDevice, serverAddress),
    timeClient(&Log)
    {}

SSSF::SSSF(String& serverAddress, DynamicJsonDocument& _attachedDevice, uint32_t _can0Baudrate):
    SSSF(serverAddress.c_str(), _attachedDevice, _can0Baudrate)
    {}

SSSF::SSSF(IPAddress& serverAddress, DynamicJsonDocument& _attachedDevice, uint32_t _can0Baudrate):
    CANNode(_can0Baudrate),
    SensorNode(),
    HTTPClient(_attachedDevice, serverAddress),
    timeClient(&Log)
    {}

SSSF::SSSF(const char* serverAddress, DynamicJsonDocument& _attachedDevice, uint32_t _can0Baudrate, uint32_t _can1Baudrate):
    CANNode(_can0Baudrate, _can1Baudrate),
    SensorNode(),
    HTTPClient(_attachedDevice, serverAddress),
    timeClient(&Log)
    {}

SSSF::SSSF(String& serverAddress, DynamicJsonDocument& _attachedDevice, uint32_t _can0Baudrate, uint32_t _can1Baudrate):
    SSSF(serverAddress.c_str(), _attachedDevice, _can0Baudrate, _can1Baudrate)
    {}

SSSF::SSSF(IPAddress& serverAddress, DynamicJsonDocument& _attachedDevice, uint32_t _can0Baudrate, uint32_t _can1Baudrate):
    CANNode(_can0Baudrate, _can1Baudrate),
    SensorNode(),
    HTTPClient(_attachedDevice, serverAddress),
    timeClient(&Log)
    {}

bool SSSF::setup()
{
    if (init() && connect())
    {
        Log.noticeln("Setting up the Teensy\'s Real Time Clock.");
        timeClient.setup();
        Log.noticeln("Setting up message sizes.");
        comBlockSize = sizeof(COMMBlock);
        comHeadSize = comBlockSize - sizeof(WCANBlock);
        Log.noticeln("Ready.");
        return true;
    }
    return false;
}

void SSSF::forwardingLoop(bool print)
{
    timeClient.update();
    pollServer();
    if (sessionStatus == Active)
    {
        struct COMMBlock msg = {0};
        struct CAN_message_t canFrame;
        pollCANNetwork(canFrame);
        int packetSize = readCOMMBlock(&msg);
        if (packetSize > 0)
        {
            // For testing
            canFrame = {0};
            write(canFrame);
            // -----------
            if (print) Serial.println(dumpCOMMBlock(msg));
            if (msg.type == 1)
            {
                //adding 28 for UDP header
                networkHealth->update(msg.index, packetSize + 28, msg.timestamp, msg.canFrame.sequenceNumber);
                can0.write(msg.canFrame.can);
                if (can1BaudRate) can1.write(msg.canFrame.can);
            }
            else if (msg.type == 2)
            {
                networkHealth->update(msg.index, packetSize + 28, msg.timestamp, msg.frameNumber);
                frameNumber = msg.frameNumber;
            }
            else if (msg.type == 3)
            {
                write(networkHealth->HealthReport);
                networkHealth->reset();
            }
        }
        if (numSignals > 0)
        {
            delete[] signals;
            numSignals = 0;
        }
    }
}

void SSSF::write(struct CAN_message_t &canFrame)
{
    struct COMMBlock msg = {0};
    msg.index = index;
    msg.frameNumber = frameNumber;
    msg.timestamp = millis();
    msg.type = 1;
    CANNode::beginPacket(msg.canFrame);
    msg.canFrame.fd = false;
    msg.canFrame.needResponse = false;
    memcpy(&msg.canFrame.can, &canFrame, canSize);
    CANNode::write(reinterpret_cast<uint8_t*>(&msg), comBlockSize);
    CANNode::endPacket();
}

void SSSF::write(struct CANFD_message_t &canFrame)
{
    struct COMMBlock msg = {0};
    msg.index = index;
    msg.frameNumber = frameNumber;
    msg.timestamp = millis();
    msg.type = 1;
    CANNode::beginPacket(msg.canFrame);
    msg.canFrame.fd = true;
    msg.canFrame.needResponse = false;
    memcpy(&msg.canFrame.canFD, &canFrame, canFDSize);
    CANNode::write(reinterpret_cast<uint8_t*>(&msg), comBlockSize);
    CANNode::endPacket();
}

void SSSF::write(NetworkStats::NodeReport *healthReport)
{
    struct COMMBlock msg = {0};
    msg.index = index;
    msg.frameNumber = frameNumber;
    msg.timestamp = millis();
    msg.type = 4;
    CANNode::beginPacket();
    int reportSize = networkHealth->size * sizeof(NetworkStats::NodeReport);
    uint8_t report[comHeadSize + reportSize];
    memcpy(report, &msg, comHeadSize);
    memcpy(report + comHeadSize, healthReport, reportSize);
    CANNode::write(report, comHeadSize + reportSize);
    CANNode::endPacket(false);
}

int SSSF::readCOMMBlock(struct COMMBlock *buffer)
{
    int remaining = CANNode::parsePacket();
    if (remaining)
    {
        uint8_t *buf = reinterpret_cast<uint8_t*>(buffer);
        int recvdHeaders = CANNode::read(buf, comHeadSize);
        if (recvdHeaders > 0)
        {
            int recvdData = 0;
            if (buffer->type == 1)
            {
                recvdData = CANNode::read(&buffer->canFrame);
            }
            else if (buffer->type == 2)
            {
                recvdData = SensorNode::read(&buffer->sensorFrame);
            }
            else if (buffer->type == 3)
            {
                return recvdHeaders;
            }
            if (recvdData > 0)
            {
                return recvdHeaders + recvdData;
            }
        }
    }
    return -1;
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
            index = 0;
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

void SSSF::pollCANNetwork(struct CAN_message_t &canFrame)
{
    if (can0BaudRate && can0.read(canFrame))
    {
        write(canFrame);
    }
    if (can1BaudRate && can1.read(canFrame))
    {
        write(canFrame);
    }
}

void SSSF::start(struct Request *request)
{
    id = request->json["ID"];
    index = request->json["Index"];
    size_t membersSize = request->json["Devices"].size();
    frameNumber = 0;
    networkHealth = new NetworkStats(membersSize);
    String ip = request->json["IP"];
    if (CANNode::startSession(ip, request->json["Port"]))
    {
        Log.noticeln("\tID: %d\tIndex: %d", id, index);
    }
}

void SSSF::stop()
{
    id = 0;
    index = 0;
    delete networkHealth;
    CANNode::stopSession();
}

String SSSF::dumpCOMMBlock(struct COMMBlock &commBlock)
{
    String msg = "Index: " + String(commBlock.index) + "\n";
    msg += "Frame Number: " + String(commBlock.frameNumber) + "\n";
    msg += "Timestamp: " + String(commBlock.timestamp) + "\n";
    msg += "Type: " + String(commBlock.type) + "\n";
    if (commBlock.type == 1)
    {
        msg += dumpCANBlock(commBlock.canFrame);
    }
    else if (commBlock.type == 2)
    {
        msg += dumpSensorBlock(commBlock.sensorFrame);
    }
    return msg;
}