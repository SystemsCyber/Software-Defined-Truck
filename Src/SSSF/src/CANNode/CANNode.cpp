#include <Arduino.h>
#include <Ethernet.h>
#include <CANNode/CANNode.h>
#include <TeensyID.h>
#include <ArduinoLog.h>
#include <FlexCAN_T4.h>
#include <Dns.h>

CANNode::CANNode(): mac{0}, sessionStatus(Inactive)
{
    Log.setPrefix(printPrefix);
    Log.setSuffix(printSuffix);
    Log.begin(LOG_LEVEL_VERBOSE, &Serial);
    Log.setShowLevel(false);
    teensyMAC(mac);
}

int CANNode::init()
{
    Log.noticeln("Setting up CAN message sizes.");
    canBlockSize = sizeof(WCANBlock);
    canSize = sizeof(CAN_message_t);
    canFDSize = sizeof(CANFD_message_t);
    canHeadSize = canBlockSize - canFDSize;
    Log.noticeln("Setting up Ethernet:");
    Log.noticeln("\t-> Initializing the Ethernet shield to use the provided MAC address");
    Log.noticeln("\t   and retreving network configuration parameters through DHCP.");
    if (Ethernet.begin(&(mac[0])))
    {
        Log.noticeln("\t***Successfully configured Ethernet using DHCP.***" CR);
        Log.noticeln("Network Configuration:");
        Log.noticeln("\tHostname: WIZnet%x%x%x", mac[3], mac[4], mac[5]);
        Log.noticeln("\tIP Address: %p", Ethernet.localIP());
        Log.noticeln("\tNetmask: %p", Ethernet.subnetMask());
        Log.noticeln("\tGateway IP: %p", Ethernet.gatewayIP());
        Log.noticeln("\tDNS Server IP: %p\n", Ethernet.dnsServerIP());
        return 1;
    }
    else
    {
        checkHardware();
        Log.fatalln("\t***Failed to configure Ethernet using DHCP***");
        return 0;
    }
}

bool CANNode::startSession(IPAddress _ip, uint16_t _port)
{
    canIP = _ip;
    canPort = _port;
    sequenceNumber = 0;

    if (canSock.beginMulticast(canIP, canPort))
    {
        sessionStatus = Active;
        Log.noticeln("Starting new session...");
        Log.noticeln("Session Information: ");
        Log.noticeln("\tIP: %p", canIP);
        Log.noticeln("\tPort: %d", canPort);
        return true;
    }
    else
    {
        Log.errorln("Failed to start new session.");
        Log.errorln("No available sockets.");
        return false;
    }
}

bool CANNode::startSession(String _ip, uint16_t _port)
{
    DNSClient dns;
    IPAddress ipConverted;
    /* Manually converts IP address here because the ethernet
       class will try to convert it before every message */
    if (!dns.inet_aton(_ip.c_str(), ipConverted))
    {
        Log.errorln("Failed to parse multicast IP address.");
        return false;
    }
    return startSession(ipConverted, _port);
}

int CANNode::parsePacket()
{
    return canSock.parsePacket();
}

int CANNode::read(uint8_t *buffer, size_t size)
{
    return canSock.read(buffer, size);
}

int CANNode::read(struct WCANBlock *buffer)
{
    uint8_t *buf = reinterpret_cast<uint8_t*>(buffer);
    int recvdHeaders = read(buf, canHeadSize);
    if (recvdHeaders > 0)
    {
        int recvdData = 0;
        if (buffer->fd)
        {
            buf = reinterpret_cast<uint8_t*>(&buffer->canFD);
            recvdData = read(buf, canFDSize);
        }
        else
        {
            buf = reinterpret_cast<uint8_t*>(&buffer->can);
            recvdData = read(buf, canSize);
        }
        if (recvdData > 0)
        {
            return recvdHeaders + recvdData;
        }
    }
    return -1;
}

int CANNode::beginPacket()
{
    return canSock.beginPacket(canIP, canPort);
}

int CANNode::beginPacket(struct WCANBlock &canBlock)
{
    canBlock.sequenceNumber = sequenceNumber;
    return beginPacket();
}

int CANNode::write(const uint8_t *buffer, size_t size)
{
    return canSock.write(buffer, size);
}

int CANNode::write(struct WCANBlock *canFrame)
{
    return write(reinterpret_cast<uint8_t*>(canFrame), sizeof(WCANBlock));
}

int CANNode::endPacket(bool incrementSequenceNumber)
{
    if (incrementSequenceNumber) sequenceNumber += 1;
    return canSock.endPacket();
}

void CANNode::stopSession()
{
    Log.noticeln("Stopping the session...");
    canSock.stop();
    canIP = IPAddress();
    canPort = 0;
    sequenceNumber = 1;
    sessionStatus = Inactive;
    Log.noticeln("Waiting for next session.");
}

String CANNode::dumpCANBlock(struct WCANBlock &canBlock)
{
    String msg = "Sequence Number: " + String(canBlock.sequenceNumber);
    msg += "Need Response: " + String(canBlock.needResponse) + "\n";
    if (canBlock.fd)
    {
        struct CANFD_message_t f = canBlock.canFD;
        msg += "CAN ID: " + String(f.id); 
        msg += " CAN Timestamp: " + String(f.timestamp) + "\n";
        msg += "Length: " + String(f.len) + " Data: ";
        for (int i = 0; i < f.len; i++)
        {
            msg += String(f.buf[i]);
        }
    }
    else
    {
        struct CAN_message_t f = canBlock.can;
        msg += "CAN ID: " + String(f.id); 
        msg += " CAN Timestamp: " + String(f.timestamp) + "\n";
        msg += "Length: " + String(f.len) + " Data: ";
        for (int i = 0; i < f.len; i++)
        {
            msg += String(f.buf[i]);
        }
    }
    msg += "\n";
    return msg;
}

void CANNode::checkHardware()
{
    Log.noticeln("\t\t-> Checking for valid Ethernet shield.");
    if (Ethernet.hardwareStatus() == EthernetNoHardware)
    {
        Log.fatalln("\t\t***Failed to find valid Ethernet shield.***");
    }
    else
    {
        Log.noticeln("\t\t***Valid Ethernet shield was detected.***");
    }
    checkLink();
}

void CANNode::checkLink()
{
    Log.noticeln("\t\t-> Checking if Ethernet cable is connected.");
    if (Ethernet.linkStatus() == LinkOFF)
    {
        Log.fatalln("\t\t***Ethernet cable is not connected or the WIZnet chip was not");
        Log.fatalln("\t\t   able to establish a link with the router or switch.***");
    }
    else
    {
        Log.noticeln("\t\t***Ethernet cable is connected and a valid link was established.***");
    }
}

// ******** From the Arduino Log Example Code ********

void CANNode::printPrefix(Print* _logOutput, int logLevel)
{
    printTimestamp(_logOutput);
    printLogLevel (_logOutput, logLevel);
}

void CANNode::printTimestamp(Print* _logOutput)
{

  // Division constants
  const unsigned int MSECS_PER_SEC       = 1000;
  const unsigned int SECS_PER_MIN        = 60;
  const unsigned int SECS_PER_HOUR       = 3600;
  const unsigned int SECS_PER_DAY        = 86400;

  // Total time
  const unsigned int msecs               =  millis() ;
  const unsigned int secs                =  msecs / MSECS_PER_SEC;

  // Time in components
  const unsigned int MiliSeconds         =  msecs % MSECS_PER_SEC;
  const unsigned int Seconds             =  secs  % SECS_PER_MIN ;
  const unsigned int Minutes             = (secs  / SECS_PER_MIN) % SECS_PER_MIN;
  const unsigned int Hours               = (secs  % SECS_PER_DAY) / SECS_PER_HOUR;

  // Time as string
  char timestamp[20];
  sprintf(timestamp, "%02u:%02u:%02u.%03u ", Hours, Minutes, Seconds, MiliSeconds);
  _logOutput->print(timestamp);
}


void CANNode::printLogLevel(Print* _logOutput, int logLevel)
{
    /// Show log description based on log level
    switch (logLevel)
    {
        default:
        case 0:_logOutput->print("SILENT " ); break;
        case 1:_logOutput->print("FATAL "  ); break;
        case 2:_logOutput->print("ERROR "  ); break;
        case 3:_logOutput->print("WARNING "); break;
        case 4:_logOutput->print("INFO "   ); break;
        case 5:_logOutput->print("TRACE "  ); break;
        case 6:_logOutput->print("VERBOSE "); break;
    }   
}

void CANNode::printSuffix(Print* _logOutput, int logLevel)
{
  _logOutput->print("");
}

// ***************************************************