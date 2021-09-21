#include <Arduino.h>
#include <EthernetUdp.h>
#include <Carla/Carla.h>
#include <HTTPClient/HTTPClient.h>
#include <Dns.h>
#include <FlexCAN_T4.h>

int Carla::init()
{
    server.init();
    bool connected = server.connect();
    if (connected && (server.response.code >= 200 && server.response.code < 400))
    {
        Serial.println("Successfully registered with the server.");
        return true;
    }
    else if (connected && !(server.response.code >= 200 && server.response.code < 400))
    {
        Serial.println("Server did not accept this devices registration.");
        Serial.println("Response Code: " + String(server.response.code));
        Serial.println("Response Reason: " + server.response.reason);
        Serial.println("Response Message: " + server.response.data);
        return false;
    }
    else
    {
        Serial.println("Failed to parse server response because " + server.response.error);
        return false;
    }
    return false;
}

int Carla::monitor(bool verbose)
{
    struct HTTPClient::Request sse;
    if (server.read(&sse))
    {
        if (sse.method.equalsIgnoreCase("POST"))
        {
            do_POST(sse);
        }
        else if (sse.method.equalsIgnoreCase("DELETE"))
        {
            do_DELETE();
        }
        else
        {
            Serial.println("Bad command received... discarding.");
        }
    }
    if (carlaPort == 0)
    {
        return false;
    }
    else
    {
        return read(verbose);
    }
}

int Carla::read(bool verbose)
{
    size_t packetSize = carla.parsePacket();
    if (packetSize)
    {
        uint8_t rxBuffer[packetSize];
        if (carla.read(rxBuffer, packetSize))
        {
            memcpy(&_frame, rxBuffer, sizeof(_frame));
        }
        else
        {
            Serial.println("parsePacket indicated available message. Failed to read them.");
        }
        if (verbose) dumpFrame(_frame);
    }
    return packetSize;
}

int Carla::write(const uint8_t *txBuffer, size_t size)
{
    if (canPort == 0)
    {
        return 0;
    }
    else
    {
        size_t newSize = size + (size_t) 12;
        uint8_t txBufferWithFrameNumber[newSize];
        memcpy(txBufferWithFrameNumber, &id, (size_t) 4);
        memcpy(txBufferWithFrameNumber+4, &_frame.frameNumber, (size_t) 4);
        memcpy(txBufferWithFrameNumber + 8, &sequenceNumber, (size_t) 4);
        sequenceNumber += 1;
        memcpy(txBufferWithFrameNumber + 12, txBuffer, size);
        can.beginPacket(mcastIP, canPort);
        if (can.write(txBufferWithFrameNumber, newSize) == 0)
        {
            Serial.println("Failed to write the message.");
        }
        int successfullySent = can.endPacket();
        if (successfullySent == 0)
        {
            Serial.println("Unknown Error occured while sending the message.");
        }
        return successfullySent;
    }
}

int Carla::write(const CAN_message_t *txBuffer)
{
    if (canPort == 0)
    {
        return 0;
    }
    else
    {
        memcpy(txCanFrameBuffer + 0, &id, (size_t) 4);
        memcpy(txCanFrameBuffer + 4, &_frame.frameNumber, (size_t) 4);
        memcpy(txCanFrameBuffer + 8, &sequenceNumber, (size_t) 4);
        sequenceNumber += 1;
        memcpy(txCanFrameBuffer + 12, txBuffer, CAN_message_t_size);
        can.beginPacket(mcastIP, canPort);
        if (can.write(txCanFrameBuffer, CAN_TX_BUFFER_SIZE) == 0)
        {
            Serial.println("Failed to write the message.");
        }
        int successfullySent = can.endPacket();
        if (successfullySent == 0)
        {
            Serial.println("Unknown Error occured while sending the message.");
        }
        return successfullySent;
    }
}

void Carla::dumpPacket(uint8_t *buffer, int packetSize, IPAddress remoteIP)
{
    Serial.print("Received packet of size ");
    Serial.print(packetSize);
    Serial.print(" bytes. From ");
    for (int i = 0; i < 4; i++)
    {
        Serial.print(remoteIP[i], DEC);
        if (i < 3)
        {
            Serial.print(".");
        }
    }
    Serial.print(", port ");
    Serial.print(remoteIP);
    Serial.println(".");

    Serial.print("Packet Data:");
    Serial.println(reinterpret_cast<char *>(buffer));
}

void Carla::dumpFrame(CARLA_UDP frame)
{
    Serial.print("Frame: ");
    Serial.println(frame.frameNumber);
    Serial.print("Throttle: ");
    Serial.print(frame.throttle, 5);
    Serial.print("  Steer:   ");
    Serial.print(frame.steer, 5);
    Serial.print("  Brake:  ");
    Serial.println(frame.brake, 5);
    Serial.print("Reverse:  ");
    Serial.print(frame.reverse);
    Serial.print("  E-Brake: ");
    Serial.print(frame.handBrake);
    Serial.print("  Manual: ");
    Serial.print(frame.manualGearShift);
    Serial.print("  Gear: ");
    Serial.println(frame.gear);
}

void Carla::do_POST(struct HTTPClient::Request sse)
{
    DNSClient dns;
    String IP = sse.data["IP"];
    if (dns.inet_aton(IP.c_str(), mcastIP))
    {
        Serial.println("Successfully parsed multicast IP address.");
    }
    else
    {
        Serial.println("Failed to parse multicast IP address.");
    }
    id = sse.data["ID"];
    canPort = sse.data["CAN_PORT"];
    carlaPort = sse.data["CARLA_PORT"];
    sequenceNumber = 0;
    if (carla.beginMulticast(mcastIP, carlaPort))
    {
        Serial.println("Successfully created a udp multicast socket.");
    }
    else
    {
        Serial.println("Failed to create a udp multicast socket.");
    }
    Serial.println("Starting new session...");
    Serial.println("Configuration: ");
    Serial.print("IP: ");
    Serial.println(mcastIP);
    Serial.print("CARLA Port: ");
    Serial.println(carlaPort);
    Serial.print("CAN Port: ");
    Serial.println(canPort);
}

void Carla::do_DELETE()
{
    Serial.print("Data operations shutting down...");
    carla.stop();
    can.stop();
    mcastIP = IPAddress();
    canPort = 0;
    carlaPort = 0;
    _frame.frameNumber = 0;
    _frame.throttle = 0.0;
    _frame.steer = 0.0;
    _frame.brake = 0.0;
    _frame.handBrake = false;
    _frame.reverse = false;
    _frame.manualGearShift = false;
    _frame.gear = (uint8_t) 0;
    sequenceNumber = 0;
    Serial.println("complete.");
    Serial.println("Waiting for next setup command.");
}