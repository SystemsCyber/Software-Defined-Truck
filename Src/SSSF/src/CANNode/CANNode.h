#ifndef CANNode_h_
#define CANNode_h_

#include <Arduino.h>
#include <EthernetUdp.h>
#include <IPAddress.h>
#include <ArduinoLog.h>
#include <FlexCAN_T4.h>
#include <SPI.h>
#include <SD.h>

#define AUTOBAUD_TIMEOUT_MS 300
#define NUM_BAUD_RATES 5
#define BAUD_RATE_LIST {250000, 500000, 125000, 666666, 1000000}

// Since the tonton FlexCAN library is a template library and we are using the
// diamond method, this has to be outside of any class.
static FlexCAN_T4<CAN0, RX_SIZE_256, TX_SIZE_16> can0;
static FlexCAN_T4<CAN1, RX_SIZE_256, TX_SIZE_16> can1;

enum SessionStatus
{
    Inactive,
    Active
};

class CANNode
{
private:
    EthernetUDP canSock;
    IPAddress canIP;
    uint16_t canPort;

    int canBlockSize = 0;
    int canHeadSize = 0;

    const uint8_t SSS3GreenLED = 2;
    const uint8_t SSS3RedLED = 5;
    const uint8_t SSS3Relay = 39;

    const uint8_t CAN2EthLED1 = 5;
    const uint8_t CAN2EthLED2 = 16;
    const uint8_t CAN2EthSilentPin1 = 14;
    const uint8_t CAN2EthSilentPin2 = 35;

    uint8_t baudRateIndex = 0;
    uint32_t baudRates[NUM_BAUD_RATES] = BAUD_RATE_LIST;
    
protected:
    uint8_t statusLED = 0;
    uint8_t rxCANLED = 0;
    uint8_t rxCANLEDStatus = LOW;

    int canSize = 0;
    int canFDSize = 0;

    int32_t can0BaudRate = -1;
    int32_t can1BaudRate = -1;

    uint8_t mac[6];  // Hostname is "WIZnet" + last three bytes of the MAC.
    uint32_t sequenceNumber = 1;
    volatile boolean sessionStatus;

    String SSSFDevice;

public:
    struct WCANBlock
    {
        uint32_t sequenceNumber;
        bool needResponse;
        bool fd;
        union
        {
            struct CAN_message_t can;
            struct CANFD_message_t canFD;
        };
    };
    
    CANNode();
    CANNode(uint32_t _can0Baudrate, String _SSSFDevice);
    CANNode(uint32_t _can0Baudrate, uint32_t _can1Baudrate, String _SSSFDevice);
    virtual int init();
    virtual bool startSession(IPAddress _ip, uint16_t _port);
    virtual bool startSession(String _ip, uint16_t _port);
    virtual int parsePacket();
    virtual int read(uint8_t *buffer, size_t size);
    virtual int read(struct WCANBlock *buffer);
    virtual int beginPacket();
    virtual int beginPacket(struct WCANBlock &canBlock);
    virtual int write(const uint8_t *buffer, size_t size);
    virtual int write(struct WCANBlock *canFrame);
    virtual int endPacket(bool incrementSequenceNumber = true);
    virtual void stopSession();
    String dumpCANBlock(struct WCANBlock &canBlock);
    void foreverFlashInError();

private:
    void setupLogging();
    void setupCANChannels();
    void ignitionOn();
    void ignitionOff();
    uint32_t getBaudRate(uint8_t channel);
    void testBaudRate(uint8_t channel, bool mode);
    static void checkHardware();
    static void checkLink();

    static void printPrefix(Print* _logOutput, int logLevel);
    static void printTimestamp(Print* _logOutput);
    static void printLogLevel(Print* _logOutput, int logLevel);
    static void printSuffix(Print* _logOutput, int logLevel);

    File initializeSD(const char *filename);
    File fileExists(const char *filename);
    File createFile(const char *filename);
};

#endif /* CANNode_h_ */

#ifndef LogStream_h_
#define LogStream_h_
class LogStream : public Print
{
public:
    File LogFile;

    LogStream() {}
    size_t print(uint8_t c)
    {
        if (c != (char) 4)
        {
            Serial.print(c);
            LogFile.print(c);
        }
        else
        {
            LogFile.flush();
        }
        return 1;
    }

    size_t write(uint8_t c)
    {
        if (c != (char) 4)
        {
            Serial.write(c);
            LogFile.write(c);
        }
        else
        {
            LogFile.flush();
        }
        return 1;
    }

    size_t write(const uint8_t *buffer, size_t size)
    {
        Serial.write(buffer, size);
        LogFile.write(buffer, size);
        LogFile.flush();
        return size;
    }
};

#endif /* LogStream_h_ */