#include <Arduino.h>
#include <EthernetUdp.h>
#include <EthernetCarla/EthernetCarla.h>
#include <HTTPClient/HTTPClient.h>

int EthernetCarla::init()
{
    int ethernetInitialization = server.init();
    if (ethernetInitialization)
    {
        if (server.enlist())
        {
            Serial.println("Successfully registered with the server.");
            return true;
        }
        else
        {
            unsuccessfulRegistration();
        }
    }
    return false;
}

int EthernetCarla::monitor(bool verbose)
{
    bool CheckForSSE = server.readSSE();
    if (server.requestError.length() > 0)
    {
        Serial.println("Bad command received... discarding.");
    }
    else if (CheckForSSE && server.requestMethod.equalsIgnoreCase("Post"))
    {
        do_POST();
    }
    else if (CheckForSSE && server.requestMethod.equalsIgnoreCase("Delete"))
    {
        do_DELETE();
    }
    return read(verbose);
}

int EthernetCarla::read(bool verbose)
{
    int packetSize = carla.parsePacket();
    if (packetSize)
    {
        carla.read(_rxBuffer, CARLA_PACKET_SIZE);
        memcpy(&_frame, _rxBuffer, sizeof(_frame));
        if (verbose)
        {
            dumpPacket(_rxBuffer, packetSize, carla.remoteIP());
            dumpFrame(_frame);
        }
    }
    return packetSize;
}

int EthernetCarla::write(const char *txBuffer, int size)
{
    return static_cast<int>(write(txBuffer, (size_t)size));
}

int EthernetCarla::write(const char *txBuffer, size_t size)
{
    can.beginPacket(mcastIP, canPort);
    can.write(txBuffer, size);
    return can.endPacket();
}

void EthernetCarla::dumpPacket(uint8_t *buffer, int packetSize, IPAddress remoteIP)
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

void EthernetCarla::dumpFrame(CARLA_UDP frame)
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

void EthernetCarla::unsuccessfulRegistration()
{
    Serial.println("Server did not accept this devices registration.");
    if (server.responseError.length() == 0)
    {
        Serial.println("Response Code: " + String(server.responseCode));
        Serial.println("Response Reason: " + server.responseReason);
        Serial.println("Response Message: " + server.responseMessage);
    }
    else
    {
        Serial.println("Failed to parse server response because " + server.responseError);
    }
}

void EthernetCarla::do_POST()
{
    mcastIP = parseIPAddress(server.requestData["IP"]);
    canPort = server.requestData["CAN_PORT"];
    carlaPort = server.requestData["CARLA_PORT"];
    Serial.println("Starting new session...");
    Serial.println("Configuration: ");
    Serial.print("IP: ");
    Serial.println(mcastIP);
    Serial.print("CARLA Port: ");
    Serial.println(carlaPort);
    Serial.print("CAN Port: ");
    Serial.println(canPort);
    carla.beginMulticast(mcastIP, carlaPort);
    can.beginMulticast(mcastIP, canPort);
}

void EthernetCarla::do_DELETE()
{
    Serial.print("Data operations shutting down...");
    carla.stop();
    can.stop();
    mcastIP = IPAddress();
    canPort = 0;
    carlaPort = 0;
    Serial.println("complete.");
    Serial.println("Waiting for next setup command.");
}

IPAddress EthernetCarla::parseIPAddress(String IP)
{
    char IP_c_str[IP.length()];
    IP.toCharArray(IP_c_str, IP.length());
    char *tokenized;
    tokenized = strtok(IP_c_str, ".");
    uint8_t IPArray[4];
    int count = 0;
    while (tokenized != NULL)
    {
        if (count > 4)
        {
            Serial.println("ERROR received incorrectly formatted IP Address.");
            return mcastIP;
        }
        IPArray[count] = (uint8_t) tokenized;
        tokenized = strtok(NULL, ".");
    }
    return IPAddress(IPArray);
}