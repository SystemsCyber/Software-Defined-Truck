#include <Arduino.h>
#include <Ethernet.h>
#include <CANNode/CANNode.h>
#include <TeensyID.h>
#include <ArduinoLog.h>
#include <FlexCAN_T4.h>
#include <Dns.h>
#include <SPI.h>
#include <SD.h>

LogStream ls;

CANNode::CANNode():
    mac{0},
    sessionStatus(Inactive)
{
    setupLogging();
    teensyMAC(mac);
}

CANNode::CANNode(uint32_t _can0Baudrate, String _SSSFDevice):
    can0BaudRate(_can0Baudrate),
    mac{0},
    sessionStatus(Inactive),
    SSSFDevice(_SSSFDevice)
{
    setupLogging();
    teensyMAC(mac);
}

CANNode::CANNode(uint32_t _can0Baudrate, uint32_t _can1Baudrate, String _SSSFDevice):
    can0BaudRate(_can0Baudrate),
    can1BaudRate(_can1Baudrate),
    mac{0},
    sessionStatus(Inactive),
    SSSFDevice(_SSSFDevice)
{
    setupLogging();
    teensyMAC(mac);
}

int CANNode::init()
{
    Log.noticeln("Setting up CAN message sizes.");
    if (SSSFDevice.compareTo("SSS3") == 0)
    {
        pinMode(SSS3GreenLED, OUTPUT);
        digitalWrite(SSS3GreenLED, LOW);
        pinMode(SSS3RedLED, OUTPUT);
        digitalWrite(SSS3RedLED, LOW);
        pinMode(SSS3Relay, OUTPUT);
        statusLED = SSS3GreenLED;
        rxCANLED = SSS3RedLED;
        Log.noticeln("SSSF Device: %s", SSSFDevice.c_str());
    }
    else if (SSSFDevice.compareTo("CAN-to-Ethernet") == 0)
    {
        pinMode(CAN2EthLED1, OUTPUT);
        digitalWrite(CAN2EthLED1, LOW);
        pinMode(CAN2EthLED2, OUTPUT);
        digitalWrite(CAN2EthLED2, LOW);
        pinMode(CAN2EthSilentPin1, OUTPUT);
        pinMode(CAN2EthSilentPin2, OUTPUT);
        digitalWrite(CAN2EthSilentPin1, LOW);
        digitalWrite(CAN2EthSilentPin2, LOW);
        statusLED = CAN2EthLED1;
        rxCANLED = CAN2EthLED2;
        Log.noticeln("SSSF Device: %s", SSSFDevice.c_str());
    }
    else
    {
        Log.fatalln("Invalid SSSF Device. Must be either SSS3 or CAN-to-Ethernet.");
        foreverFlashInError();
        return 0;
    }
    Log.noticeln("Setting up CAN Channel(s).");
    setupCANChannels();
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
        foreverFlashInError();
        return 0;
    }
}

bool CANNode::startSession(IPAddress _ip, uint16_t _port)
{
    canIP = _ip;
    canPort = _port;
    sequenceNumber = 1;

    if (canSock.beginMulticast(canIP, canPort))
    {
        sessionStatus = Active;
        Log.noticeln("Starting new session...");
        Log.noticeln("Session Information: ");
        Log.noticeln("\tIP: %p", canIP);
        Log.noticeln("\tPort: %d", canPort);
        ignitionOn();
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
    dns.begin(Ethernet.dnsServerIP());
    IPAddress ipConverted;
    /* Manually converts IP address here because the ethernet
       class will try to convert it before every message */
    if (dns.inet_aton(_ip.c_str(), ipConverted) != 1)
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

int CANNode::unpackCANBlock(struct WCANBlock &frame, uint8_t *msgBuffer)
{
    int size = CANNode::read(msgBuffer, canBlockPackedSize);
    if (size > 6)
    {
        memcpy(&frame.sequenceNumber, msgBuffer, 4);
        memcpy(&frame.fd, &msgBuffer[4], 1);
        memcpy(&frame.needResponse, &msgBuffer[5], 1);
        if (frame.fd)
        {
            memcpy(&frame.canFD.id, &msgBuffer[6], 4);
            memcpy(&frame.canFD.len, &msgBuffer[10], 1);
            memcpy(&frame.canFD.flags, &msgBuffer[11], 1);
            memcpy(&frame.canFD.buf, &msgBuffer[12], frame.canFD.len);
        }
        else
        {
            memcpy(&frame.can.id, &msgBuffer[6], 4);
            memcpy(&frame.can.len, &msgBuffer[10], 1);
            memcpy(&frame.can.buf, &msgBuffer[11], frame.can.len);
        }
    }
    return size;
}

int CANNode::packCANBlock(struct WCANBlock &frame, uint8_t *msgBuffer)
{
    memcpy(msgBuffer, &frame.sequenceNumber, 4);
    memcpy(&msgBuffer[4], &frame.fd, 1);
    memcpy(&msgBuffer[5], &frame.needResponse, 1);
    if (frame.fd)
    {
        memcpy(&msgBuffer[6], &frame.canFD.id, 4);
        memcpy(&msgBuffer[10], &frame.canFD.len, 1);
        memcpy(&msgBuffer[11], &frame.canFD.flags, 1);
        memcpy(&msgBuffer[12], &frame.canFD.buf, frame.canFD.len);
        return 12 + frame.canFD.len;
    }
    else
    {
        memcpy(&msgBuffer[6], &frame.can.id, 4);
        memcpy(&msgBuffer[10], &frame.can.len, 1);
        memcpy(&msgBuffer[11], &frame.can.buf, frame.can.len);
        return 11 + frame.can.len;
    }
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
    ignitionOff();
    digitalWrite(rxCANLED, LOW);
    Log.noticeln("Waiting for next session.");
}

String CANNode::dumpCANBlock(struct WCANBlock &canBlock)
{
    String msg = "Sequence Number: " + String(canBlock.sequenceNumber);
    msg += " Need Response: " + String(canBlock.needResponse);
    msg += " FD: " + String(canBlock.fd) + "\n" + "Frame:\n";
    if (canBlock.fd)
    {
        struct CANFD_message f = canBlock.canFD;
        msg += "\tCAN ID: " + String(f.id) + "\n";
        msg += "\tLength: " + String(f.len) + " Data: ";
        for (int i = 0; i < f.len; i++)
        {
            msg += String(f.buf[i]);
        }
        msg += "\n";
    }
    else
    {
        struct CAN_message f = canBlock.can;
        msg += "\tCAN ID: " + String(f.id) + "\n";
        msg += "\tLength: " + String(f.len) + " Data: ";
        for (int i = 0; i < f.len; i++)
        {
            msg += String(f.buf[i]);
        }
        msg += "\n";
    }
    return msg;
}

void CANNode::setupLogging()
{
    ls.LogFile = initializeSD("SSSF.log");
    Log.setPrefix(printPrefix);
    Log.setSuffix(printSuffix);
    Log.begin(LOG_LEVEL_VERBOSE, &ls);
    Log.setShowLevel(false);
}

void CANNode::setupCANChannels()
{
    can0.begin();
    if (can0BaudRate == 0)
    {
        Log.noticeln("Baudrate of 0 was given. Using autobaud to determine the bitrate.");
        ignitionOn();
        can0BaudRate = getBaudRate(0);
        ignitionOff();
    }
    Log.noticeln("Setting up can0 with a bitrate of %d", can0BaudRate);
    can0.setBaudRate(can0BaudRate);
    if (can1BaudRate >= 0)
    {
        can1.begin();
        if (can1BaudRate == 0)
        {
            Log.noticeln("Baudrate of 0 was given. Using autobaud to determine the bitrate.");
            ignitionOn();
            can1BaudRate = getBaudRate(1);
            ignitionOff();
        }
        Log.noticeln("Setting up can1 with a bitrate of %d", can1BaudRate);
        can1.setBaudRate(can1BaudRate);
    }
    // while(true) {
    //     CAN_message_t msg;
    //     if (can0.read(msg)) {
    //         Log.noticeln("CAN0: %d %d %d %d %d %d %d %d", msg.buf[0], msg.buf[1], msg.buf[2], msg.buf[3], msg.buf[4], msg.buf[5], msg.buf[6], msg.buf[7]);
    //     }
    //     if (can1.read(msg)) {
    //         Log.noticeln("CAN1: %d %d %d %d %d %d %d %d", msg.buf[0], msg.buf[1], msg.buf[2], msg.buf[3], msg.buf[4], msg.buf[5], msg.buf[6], msg.buf[7]);
    //     }
    // }
}

void CANNode::ignitionOn()
{
    if (SSSFDevice.compareTo("SSS3") == 0)
    {
        digitalWrite(SSS3Relay, HIGH);
        delay(3000);
    }
}

void CANNode::ignitionOff()
{
    if (SSSFDevice.compareTo("SSS3") == 0)
    {
        digitalWrite(SSS3Relay, LOW);
        delay(3000);
    }
}

uint32_t CANNode::getBaudRate(uint8_t channel)
{
    // Not clean code due to the limitation of the templated FLEXCAN library
    if (channel == 0)
    {
        Log.infoln("Emptying the read buffer of old messages...");
        CAN_message_t rxmsg;
        while (can0.read(rxmsg));
        Log.infoln("Starting autobaud routine...");
        uint32_t routine_start_time = millis();
        while((millis() - routine_start_time) < (AUTOBAUD_TIMEOUT_MS * NUM_BAUD_RATES))
        {
            Log.infoln("Trying baud rate %d", baudRates[baudRateIndex]);
            can0.setBaudRate(baudRates[baudRateIndex]);
            Log.infoln("Resetting the error counters.");
            can0.FLEXCAN_EnterFreezeMode();
            FLEXCANb_ECR(CAN0) = 0;
            can0.FLEXCAN_ExitFreezeMode();
            uint8_t previousRec = (FLEXCANb_ECR(CAN0) & 0x0000FF00) >> 8;
            Log.infoln("Waiting for a message to arrive... (timeout: %d ms)", AUTOBAUD_TIMEOUT_MS);
            uint32_t frameStartTime = millis();
            while((millis() - frameStartTime) < AUTOBAUD_TIMEOUT_MS)
            {
                if (can0.read(rxmsg))
                {
                    Log.infoln("Message received. Baud rate is %d", baudRates[baudRateIndex]);
                    return baudRates[baudRateIndex];
                }
                else
                {
                    uint8_t currentREC = (FLEXCANb_ECR(CAN0) & 0x0000FF00) >> 8;
                    if ((currentREC - previousRec) > 0)
                    {
                        Log.infoln("Error counter increased. Trying next baud rate...");
                        break;
                    }
                }
            }
            Log.infoln("No message received. Trying next baud rate...");
            baudRateIndex++;
            if (baudRateIndex > NUM_BAUD_RATES)
            {
                baudRateIndex = 0;
            }
        }
        Log.fatalln("No baud rate found. Aborting.");
        foreverFlashInError();
    }
    else if (channel == 1)
    {
        Log.infoln("Emptying the read buffer of old messages...");
        CAN_message_t rxmsg;
        while (can1.read(rxmsg));
        Log.infoln("Starting autobaud routine...");
        uint32_t routine_start_time = millis();
        while((millis() - routine_start_time) < (AUTOBAUD_TIMEOUT_MS * NUM_BAUD_RATES))
        {
            Log.infoln("Trying baud rate %d", baudRates[baudRateIndex]);
            can1.setBaudRate(baudRates[baudRateIndex]);
            Log.infoln("Resetting the error counters.");
            can1.FLEXCAN_EnterFreezeMode();
            FLEXCANb_ECR(CAN1) = 0;
            can1.FLEXCAN_ExitFreezeMode();
            uint8_t previousRec = (FLEXCANb_ECR(CAN1) & 0x0000FF00) >> 8;
            Log.infoln("Waiting for a message to arrive... (timeout: %d ms)", AUTOBAUD_TIMEOUT_MS);
            uint32_t frameStartTime = millis();
            while((millis() - frameStartTime) < AUTOBAUD_TIMEOUT_MS)
            {
                if (can1.read(rxmsg))
                {
                    Log.infoln("Message received. Baud rate is %d", baudRates[baudRateIndex]);
                    return baudRates[baudRateIndex];
                }
                else
                {
                    uint8_t currentREC = (FLEXCANb_ECR(CAN1) & 0x0000FF00) >> 8;
                    if ((currentREC - previousRec) > 0)
                    {
                        // Error detected, try next baud rate
                        break;
                    }
                }
            }
            Log.infoln("No message received. Trying next baud rate...");
            baudRateIndex++;
            if (baudRateIndex > NUM_BAUD_RATES)
            {
                baudRateIndex = 0;
            }
        }
        Log.fatalln("No baud rate found. Aborting.");
        foreverFlashInError();
    }
    return baudRates[baudRateIndex];
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

void CANNode::foreverFlashInError()
{
    Log.fatalln("\t\t***The CANNode is in an error state and will now flash the LED.***");
    while (1)
    {
        digitalWrite(statusLED, HIGH);
        digitalWrite(rxCANLED, LOW);
        delay(250);
        digitalWrite(statusLED, LOW);
        digitalWrite(rxCANLED, HIGH);
        delay(250);
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
    _logOutput->print((char)4);
}

File CANNode::initializeSD(const char *filename)
{
    Serial.print("Initializing SD card for logging...");
    if (!SD.begin(BUILTIN_SDCARD))
    {
        Serial.println("card failed, or not present.");
        foreverFlashInError();
    }
    else
    {
        Serial.println("card initialized.");
    }
    return fileExists(filename);
}

File CANNode::fileExists(const char *filename)
{
    Serial.println("Checking for SSSF.log file...");
    if (!SD.exists(filename))
    {
        Serial.println("SSSF.log file not found. Creating new file...");
    }
    else
    {
        Serial.println("SSSF.log file found. Removing old file...");
        SD.remove(filename);
        Serial.println("SSSF.log file removed. Creating new file...");
    }
    return createFile(filename);
}

File CANNode::createFile(const char *filename)
{
    File file = SD.open(filename, FILE_WRITE_BEGIN);
    if (file)
    {
        Serial.print("Creating ");
        Serial.print(filename);
        Serial.println("...");
    }
    else
    {
        Serial.print("Error creating ");
        Serial.print(filename);
        Serial.println("...");
        foreverFlashInError();
    }
    return file;
}