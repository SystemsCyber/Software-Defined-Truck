#include <Arduino.h>
#include <Ethernet.h>
#include <EthernetUdp.h>
#include <EthernetCarla/EthernetCarla.h>
#include <Configuration/LoadConfiguration.h>
#include <Dns.h>
#include <string>

int EthernetCarla::init()
{
    LoadConfiguration config(_filename);
    _config = config;
    Serial.println("Setting up Ethernet:");
    Serial.println("\t-> Initializing the Ethernet shield to use the provided MAC address");
    Serial.println("\t   and retreving network configuration parameters through DHCP.");
    int success = ethernetBegin(Ethernet.begin(_config.mac.data()));
    if (success)
    {
        registerWithServer();
    }
    return success;
}

int EthernetCarla::monitor(bool verbose)
{
    if (checkForCommand())
    {
        mcastIP = _mcast.mcastIP;
        if (_mcast.mcastIP[0] == 0)
        {
            stopDataOperations();
        }
        else if ((_mcast.carlaPort == 0) || (_mcast.canPort == 0))
        {
            Serial.print("Bad command received... discarding.");
            return 0;
        }
        else
        {
            startDataOperations();
        }
    }
    return read(verbose);
}

int EthernetCarla::read(bool verbose)
{
    int packetSize = _carla.parsePacket();
    if (packetSize)
    {
        _carla.read(_rxBuffer, CARLA_PACKET_SIZE);
        memcpy(&_frame, _rxBuffer, sizeof(_frame));
        if (verbose)
        {
            dumpPacket(_rxBuffer, packetSize, _carla.remoteIP());
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
    _can.beginPacket(mcastIP, _mcast.canPort);
    _can.write(txBuffer, size);
    return _can.endPacket();
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

int EthernetCarla::ethernetBegin(int success)
{
    if (success) // Ethernet begin returns 0 when successful
    {
        checkHardware();
        Serial.println("\t***Successfully configured Ethernet using DHCP.***");
        Serial.println();
        Serial.println("Network Configuration:");
        Serial.print("\tHostname: ");
        Serial.print("WIZnet");
        Serial.print(_config.mac[3], HEX);
        Serial.print(_config.mac[4], HEX);
        Serial.println(_config.mac[5], HEX);
        Serial.print("\tIP Address: ");
        Serial.println(Ethernet.localIP());
        Serial.print("\tNetmask: ");
        Serial.println(Ethernet.subnetMask());
        Serial.print("\tGateway IP: ");
        Serial.println(Ethernet.gatewayIP());
        Serial.print("\tDNS Server IP: ");
        Serial.println(Ethernet.dnsServerIP());
    }
    else
    {
        checkHardware();
        Serial.println("\t***Failed to configure Ethernet using DHCP***");
        
    }
    return success;
}

void EthernetCarla::checkHardware()
{
    Serial.println("\t\t-> Checking for valid Ethernet shield.");
    if (Ethernet.hardwareStatus() == EthernetNoHardware)
    {
        Serial.println("\t\t***Failed to find valid Ethernet shield.***");
    }
    else
    {
        Serial.println("\t\t***Valid Ethernet shield was detected.***");
    }
    checkLink();
}

void EthernetCarla::checkLink()
{
    Serial.println("\t\t-> Checking if Ethernet cable is connected.");
    if (Ethernet.linkStatus() == LinkOFF)
    {
        Serial.println("\t\t***Ethernet cable is not connected or the WIZnet chip was not");
        Serial.println("\t\t   able to establish a link with the router or switch.***");
    }
    else
    {
        Serial.println("\t\t***Ethernet cable is connected and a valid link was established.***");
    }
}

void EthernetCarla::registerWithServer()
{
    if (!(_config.FQDN[0] >= '0' && _config.FQDN[0] <= '9'))
    {
        DNSClient dns;
        dns.begin(Ethernet.dnsServerIP());
        dns.getHostByName(_config.FQDN, _config.serverIP);
    }
    unsigned long lastAttempt = 0;
    const unsigned long retryInterval = 60 * 1000;
    bool keepTrying = sendConfig(&lastAttempt);
    while (keepTrying)
    {
        if (millis() - lastAttempt > retryInterval)
        {
            keepTrying = sendConfig(&lastAttempt);
        }
    }
}

bool EthernetCarla::sendConfig(unsigned long *lastAttempt)
{
    Serial.print("Connecting to the Control Server at ");
    Serial.print(_config.serverIP);
    Serial.print("... ");
    if (_controller.connect(_config.serverIP, _config.serverPort))
    {
        Serial.println("connected.");
        // Serial.print("Generating configuration message... ");
        // struct device_config
        // {
        //     uint8_t mac[6];
        //     struct LoadConfiguration::DEVICE attachedDevice;
        // } config;
        // memcpy(config.mac, _config.mac.data(), sizeof(config.mac));
        // memcpy(&config.attachedDevice, &_config.attachedDevice, sizeof(_config.attachedDevice));
        // Serial.println("complete.");
        Serial.print("Sending configuration message... ");
        // _controller.write(reinterpret_cast<uint8_t *>(&config), sizeof(config));
        _controller.write("POST /sss3/register HTTP/1.1\r\nConnection: keep-alive\r\n\r\n" + config.config_as_string);
        _controller.flush();
        Serial.println("complete.");
        return false;
    }
    else
    {
        *lastAttempt = millis();
        Serial.println("connection failed.");
        Serial.println("Retrying in 60 seconds.");
        Serial.println();
        return true;
    }
}

bool EthernetCarla::checkForCommand()
{
    Ethernet.maintain(); //Keep current address assigned by DHCP server.
    if (_controller.available())
    {
        int commandSize = _controller.read(setupBuffer, SETUP_PACKET_SIZE);
        if (commandSize == 16)
        {
            Serial.print("New command from: ");
            Serial.println(_controller.remoteIP());
            memcpy(&_mcast, setupBuffer, sizeof(_mcast));
            Serial.println("Acknowledging that the command has been received.");
            _controller.write((uint8_t)1);
            return true;
        }
        else
        {
            discardPacket(_controller, commandSize);
        }
    }
    else if (!_controller.connected())
    {
        Serial.println("Lost connection to the Control Server. Trying to re-connect...");
        registerWithServer();
    }
    else
    {
        // heartbeat();
    }
    return false;
}

void EthernetCarla::startDataOperations()
{
    Serial.println("Data operations starting...");
    Serial.println("Configuration: ");
    Serial.print("IP: ");
    Serial.println(mcastIP);
    Serial.print("CARLA Port: ");
    Serial.println(_mcast.carlaPort);
    Serial.print("CAN Port: ");
    Serial.println(_mcast.canPort);
    _carla.beginMulticast(mcastIP, _mcast.carlaPort);
    _can.beginMulticast(mcastIP, _mcast.canPort);
}

void EthernetCarla::stopDataOperations()
{
    Serial.print("Data operations shutting down...");
    _carla.stop();
    _can.stop();
    Serial.println("complete.");
    Serial.println("Waiting for next setup command.");
}

void EthernetCarla::heartbeat()
{
    if (millis() - _lastHeartbeat > _heartbeatInterval)
    {
        Serial.print("Sending heartbeat... ");
        _controller.write(reinterpret_cast<char *>(&_config.mac));
        _controller.flush();
        Serial.println("complete.");
        _lastHeartbeat = millis();
    }
}

void EthernetCarla::discardPacket(EthernetClient &newCommand, int commandSize)
{
    Serial.print("A packet has been received from ");
    Serial.print(newCommand.remoteIP());
    Serial.println(", but has been discarded due to it being the wrong size.");
    Serial.print("Packet size received: ");
    Serial.print(commandSize);
    Serial.println(" bytes.");
    Serial.println("Packet size required: ");
    Serial.print(SETUP_PACKET_SIZE);
    Serial.println(" bytes.");
}