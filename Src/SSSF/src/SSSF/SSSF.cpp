#include <Arduino.h>
#include <SSSF/SSSF.h>
#include <SensorNode/SensorNode.h>
#include <CANNode/CANNode.h>
#include <HTTP/HTTPClient.h>
#include <NetworkStats/NetworkStats.h>
#include <TimeClient/TimeClient.h>
#include <EthernetUdp.h>
#include <ArduinoJson.h>
#include <Dns.h>
#include <FlexCAN_T4.h>

#define DELAY_REQ_DELAY 65
#define CAN_SEND_DELAY 85

struct CAN_message_t canFrame;
struct CANNode::CAN_message canMsg;
struct SSSF::COMMBlock msg;

SSSF::SSSF(const char* serverAddress, DynamicJsonDocument& _config, uint32_t _can0Baudrate):
    CANNode(_can0Baudrate, _config["SSSFDevice"].as<String>()),
    SensorNode(),
    HTTPClient(_config, serverAddress),
    ptpClient(&Log)
    {}

SSSF::SSSF(String& serverAddress, DynamicJsonDocument& _config, uint32_t _can0Baudrate):
    SSSF(serverAddress.c_str(), _config, _can0Baudrate)
    {}

SSSF::SSSF(IPAddress& serverAddress, DynamicJsonDocument& _config, uint32_t _can0Baudrate):
    CANNode(_can0Baudrate, _config["SSSFDevice"].as<String>()),
    SensorNode(),
    HTTPClient(_config, serverAddress),
    ptpClient(&Log)
    {}

SSSF::SSSF(const char* serverAddress, DynamicJsonDocument& _config, uint32_t _can0Baudrate, uint32_t _can1Baudrate):
    CANNode(_can0Baudrate, _can1Baudrate, _config["SSSFDevice"].as<String>()),
    SensorNode(),
    HTTPClient(_config, serverAddress),
    ptpClient(&Log)
    {}

SSSF::SSSF(String& serverAddress, DynamicJsonDocument& _config, uint32_t _can0Baudrate, uint32_t _can1Baudrate):
    SSSF(serverAddress.c_str(), _config, _can0Baudrate, _can1Baudrate)
    {}

SSSF::SSSF(IPAddress& serverAddress, DynamicJsonDocument& _config, uint32_t _can0Baudrate, uint32_t _can1Baudrate):
    CANNode(_can0Baudrate, _can1Baudrate, _config["SSSFDevice"].as<String>()),
    SensorNode(),
    HTTPClient(_config, serverAddress),
    ptpClient(&Log)
    {}

bool SSSF::setup()
{
    if (init() && connect())
    {
        Log.noticeln("Setting up the Teensy\'s Real Time Clock.");
        Log.noticeln("Setting up message sizes.");
        Log.noticeln("Ready.");
        return true;
    }
    return false;
}

void SSSF::forwardingLoop(bool print)
{
    pollServer();
    // struct CAN_message_t canFrame;
    // if (can0.read(canFrame))
    // {
    //     // while (can0.read(canFrame)) {}
    //     Serial.println(canFrame.id, HEX);
    //     canFrame.id = 0x18F00485;
    //     Serial.println(can0.write(canFrame));
    // }
    if (sessionStatus == Active)
    {
        // For testing
        // if (millis() - lastSend >= sendInterval)
        // {
        //     lastSend = millis();
        //     struct CAN_message_t canFrame;
        //     canFrame.mb = 0;
        //     canFrame.id = 0x1FFFFFFF;
        //     canFrame.len = 8;
        //     canFrame.flags.extended = true;
        //     write(canFrame);
        // }
        // -----------
        pollCANNetwork();
        int packetSize = read();
        if (packetSize > 0)
        {
            if (print) Serial.println(dumpCOMMBlock(msg));
            if (msg.type == 1)
            {
                memset(&canFrame, 0, sizeof(canFrame));
                networkHealth->update(msg.index, packetSize, msg.timestamp, msg.canFrame.sequenceNumber, msgReceivedTime);
                canFrame.id = msg.canFrame.can.id;
                canFrame.len = msg.canFrame.can.len;
                memcpy(canFrame.buf, msg.canFrame.can.buf, msg.canFrame.can.len);
                can0.write(canFrame);
                if (can1BaudRate > 0) can1.write(canFrame);
            }
            else if (msg.type == 2)
            {
                networkHealth->update(msg.index, packetSize, msg.timestamp, msg.frameNumber, msgReceivedTime);
                frameNumber = msg.frameNumber;
                // // Apply transformation
                // canFrame.mb = 0;
                // canFrame.id = 0x18F00300 ^ 0x1FFFFFFF;
                // canFrame.len = 8;
                // canFrame.flags.extended = true;
                // uint8_t throttle = uint8_t((msg.sensorFrame.signals[0] * 100.0) / 0.4);
                // canFrame.buf[1] = throttle;
                // canFrame.buf[6] = 255;
                // canFrame.buf[7] = 255;
                // write(canFrame);
                // can0.write(canFrame);
                // if (can1BaudRate > 0) can1.write(canFrame);
                // -----------
            }
            else if (msg.type == 3)
            {
                write(networkHealth->HealthReport);
                networkHealth->reset();
            }
            else if (msg.type == 5)
            {
                ptpClient.syncUpdate(msg.timestamp, msgReceivedTime);
            }
            else if (msg.type == 6)
            {
                if (ptpClient.followUpUpdate(msg.timeFrame, msg.timestamp))
                {
                    sendDelayReq();
                }
            }
            else if (msg.type == 8 && msg.index == index && 
                        msg.timeFrame == ptpClient.delayReqTimestamp)
            {
                ptpClient.delayUpdate(msg.timestamp);
            }
        }
    }
}

void SSSF::write(struct CAN_message &canFrame)
{
    memset(&msg, 0, sizeof(msg));
    msg.index = index;
    msg.frameNumber = frameNumber;
    msg.timestamp = ptpClient.getEpochTimeUS() + CAN_SEND_DELAY;
    msg.type = 1;
    CANNode::beginPacket(msg.canFrame);
    msg.canFrame.fd = false;
    msg.canFrame.needResponse = false;
    msg.canFrame.can.id = canFrame.id;
    msg.canFrame.can.len = canFrame.len;
    memcpy(msg.canFrame.can.buf, canFrame.buf, canFrame.len);
    size_t size = packCOMMBlock(msg);
    CANNode::write(msgBuffer, size);
    CANNode::endPacket();
}

void SSSF::write(struct CANFD_message &canFrame)
{
    memset(&msg, 0, sizeof(msg));
    msg.index = index;
    msg.frameNumber = frameNumber;
    msg.timestamp = ptpClient.getEpochTimeUS();
    msg.type = 1;
    CANNode::beginPacket(msg.canFrame);
    msg.canFrame.fd = true;
    msg.canFrame.needResponse = false;
    msg.canFrame.canFD.id = canFrame.id;
    msg.canFrame.canFD.len = canFrame.len;
    memcpy(msg.canFrame.canFD.buf, canFrame.buf, canFrame.len);
    size_t size = packCOMMBlock(msg);
    CANNode::write(msgBuffer, size);
    CANNode::endPacket();
}

void SSSF::write(NetworkStats::NodeReport *healthReport)
{
    memset(&msg, 0, sizeof(msg));
    msg.index = index;
    msg.frameNumber = frameNumber;
    msg.timestamp = ptpClient.getEpochTimeUS();
    msg.type = 4;
    CANNode::beginPacket();
    size_t size = packCOMMBlock(msg);
    CANNode::write(msgBuffer, size);
    CANNode::endPacket(false);
}

size_t SSSF::packCOMMBlock(struct COMMBlock &msg)
{
    size_t size = 0;
    memcpy(msgBuffer, &msg.index, 1);
    memcpy(&msgBuffer[1], &msg.type, 1);
    memcpy(&msgBuffer[2], &msg.frameNumber, 4);
    memcpy(&msgBuffer[6], &msg.timestamp, 8);
    size += comPackedHeadSize;
    if (msg.type == 1)
    {
        size += packCANBlock(msg.canFrame, &msgBuffer[size]);
    }
    else if (msg.type == 2)
    {
        size += packSensorBlock(msg.sensorFrame, &msgBuffer[size]);
    }
    else if (msg.type == 4)
    {
        memcpy(&msgBuffer[size], networkHealth->HealthReport, reportSize);
        size += reportSize;
    }
    return size;
}

int SSSF::read()
{
    if (CANNode::parsePacket())
    {
        msgReceivedTime = ptpClient.getEpochTimeUS();
        return unpackCOMMBlock();
    }
    return -1;
}

int SSSF::unpackCOMMBlock()
{
    int size = CANNode::read(msgBuffer, comPackedHeadSize);
    if (size >= comPackedHeadSize)
    {
        memcpy(&msg.index, msgBuffer, 1);
        memcpy(&msg.type, &msgBuffer[1], 1);
        memcpy(&msg.frameNumber, &msgBuffer[2], 4);
        memcpy(&msg.timestamp, &msgBuffer[6], 8);
        if (msg.type == 1)
        {
            size += unpackCANBlock(msg.canFrame, &msgBuffer[comPackedHeadSize]);
        }
        else if (msg.type == 2)
        {
            size += unpackSensorBlock(msg.sensorFrame, &msgBuffer[comPackedHeadSize]);
        }
        else if (msg.type == 6 || msg.type == 8)
        {
            int num_size = CANNode::read(&msgBuffer[comPackedHeadSize], 8);
            if (num_size == 8)
            {
                memcpy(&msg.timeFrame, &msgBuffer[comPackedHeadSize], 8);
            }
            size += num_size;
        }
        return size;
    }
    return -1;
}

void SSSF::sendDelayReq()
{
    memset(&msg, 0, sizeof(msg));
    msg.index = index;
    msg.frameNumber = frameNumber;
    ptpClient.delayReqTimestamp = ptpClient.getEpochTimeUS()  + DELAY_REQ_DELAY;
    msg.timestamp = ptpClient.delayReqTimestamp;
    msg.type = 7;
    CANNode::beginPacket();
    size_t size = packCOMMBlock(msg);
    CANNode::write(msgBuffer, size);
    CANNode::endPacket(false);
    ptpClient.transmit = ptpClient.getEpochTimeUS();
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

void SSSF::pollCANNetwork()
{ // If messages build up in the queue this should be a while loop
    if ((can0BaudRate > 0) && can0.read(canFrame))
    {
        canMsg.id = canFrame.id;
        canMsg.len = canFrame.len;
        memcpy(canMsg.buf, canFrame.buf, canFrame.len);
        digitalWrite(rxCANLED, rxCANLEDStatus);
        rxCANLEDStatus = !rxCANLEDStatus;
        write(canMsg);
    }
    if ((can1BaudRate > 0) && can1.read(canFrame))
    {
        canMsg.id = canFrame.id;
        canMsg.len = canFrame.len;
        memcpy(canMsg.buf, canFrame.buf, canFrame.len);
        write(canMsg);
    }
}

void SSSF::start(struct Request *request)
{
    id = request->json["ID"];
    index = request->json["Index"];
    size_t membersSize = request->json["Devices"].size();
    reportSize = membersSize * sizeof(NetworkStats::NodeReport);
    comPackedMaxSize = max(comPackedMaxSize, comPackedHeadSize + reportSize);
    msgBuffer = new uint8_t[comPackedMaxSize]();
    frameNumber = 0;
    ptpClient.start(membersSize, index);
    networkHealth = new NetworkStats(membersSize, &ptpClient);
    String ip = request->json["IP"];
    if (CANNode::startSession(ip, request->json["Port"]))
    {
        Log.noticeln("\tID: %d\tIndex: %d", id, index);
    }
}

void SSSF::stop()
{
    ptpClient.stop();
    id = 0;
    index = 0;
    delete networkHealth;
    if (msgBuffer != nullptr)
        delete[] msgBuffer;
    CANNode::stopSession();
}

String SSSF::dumpCOMMBlock(struct COMMBlock &commBlock)
{
    String msg = "Index: " + String(commBlock.index) + "\n";
    msg += "Frame Number: " + String(commBlock.frameNumber) + "\n";
    char timestamp[20];
    sprintf(timestamp, "%" PRIu64, commBlock.timestamp);
    msg += "Timestamp: " + String(timestamp) + "\n";
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