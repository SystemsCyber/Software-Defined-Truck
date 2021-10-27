#include <Arduino.h>
#include <EthernetUdp.h>
#include <SSSF/SSSF.h>
#include <TimeLib.h>
#include <NTPClient.h>
#include <HTTP/HTTPClient.h>
#include <Dns.h>
#include <FlexCAN_T4.h>

SSSF::SSSF(): SensorNode(), timeClient(ntpSock)
{
    timeClient.begin();
    setSyncProvider(getExternalTime(Teensy3Clock.get()));
    setSyncInterval(1);
}

void SSSF::maintain()
{
    if (timeClient.update())
    {
        Teensy3Clock.set(timeClient.getEpochTime());
        setTime(timeClient.getEpochTime());
        Ethernet.maintain(); //Only tries to renew if 3/4 through lease
    }
}

int SSSF::init()
{
    server.init();
    bool connected = server.connect();
    if (connected && (server.response.code >= 200 && server.response.code < 400))
    {
        Serial.println("Successfully registered with the server.");
        return true;
    }
    else if (connected && (server.response.error == ""))
    {
        Serial.println("Server did not accept this devices registration.");
        Serial.print("Response Code: ");
        Serial.println(String(server.response.code));
        Serial.print("Response Reason: ");
        Serial.println(server.response.reason);
        Serial.print("Response Message: ");
        Serial.println(server.response.data);
        return false;
    }
    else
    {
        Serial.print("Failed to parse server response because ");
        Serial.println(server.response.error);
        return false;
    }
    return false;
}

int SSSF::monitor(bool verbose)
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

int SSSF::read(bool verbose)
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

int SSSF::write(const uint8_t *txBuffer, size_t size)
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

int SSSF::write(const CAN_message_t *txBuffer)
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

void SSSF::dumpPacket(uint8_t *buffer, int packetSize, IPAddress remoteIP)
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

void SSSF::dumpFrame(CARLA_UDP frame)
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

void SSSF::do_POST(struct HTTPClient::Request sse)
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
    int carlaMulticast = carla.beginMulticast(mcastIP, carlaPort);
    int canMulticast = can.beginMulticast(mcastIP, canPort);
    if (carlaMulticast && canMulticast)
    {
        Serial.println("Successfully created udp multicast sockets.");
    }
    else
    {
        Serial.println("Failed to create the udp multicast sockets.");
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

void SSSF::do_DELETE()
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