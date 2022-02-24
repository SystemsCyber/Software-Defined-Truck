#ifndef NTPCLIENT_H_
#define NTPCLIENT_H_

#include <Arduino.h>
#include <EthernetUdp.h>
#include <ArduinoLog.h>
#include <IPAddress.h>

#define SEVENZYYEARS 2208988800UL
#define NTP_PACKET_SIZE 48
#define NTP_DEFAULT_LOCAL_PORT 1337
#define MILLISPERSEC 1000
#define MICROSPERMILLIS 1000
#define MICROSPERSEC 1000000
#define SEVENTYYEARSMICROS 2208988800000000ULL

/*
NTP notes:
Originate Timestamp (t1): time when ntp packet sent from client
Receive Timestamp (t2): time when ntp packet was received by server
Transmit Timestamp (t3): time when the ntp packet was sent from the server
Reference Timestamp: the time when the system clock on the server was last set or corrected
Destination Timestamp (t4): the time when the ntp pack was received from the server.

offset = ((t2 - t1) + (t3 - t4)) / 2
delay = (t3 - t2) + (t4 - t1)
The offset is calculated from the packet with the smallest delay out of the last eight packets.

Smallest polling time is 16 seconds. Which should only be done until the clock is accurate.
Smallest constant polling time is 64 seconds.
Recommended smallest constant polling time is 128 seconds.

NTP time is from jan 1st 1900
System time is from jan 1st 1970
NTP delta is 70 years is seconds which is 2208988800

Teensy RTC
Frquency is 32.768KHz
Gets off by about 5 minutes per month
Accuracy is very temperature dependent
Precision is 1/32768 which is 0.000030517578125 or about 30 microseconds.
*/

enum NTPStatus
{
    NotSet,
    Sent,
    Received,
    Timedout
};

class TimeClient
{
private:
    NTPStatus status = NotSet;
    uint64_t originate = 0ULL;
    uint64_t receive = 0ULL;
    uint64_t transmit = 0ULL;
    struct NTPPacket
    {
        int64_t offset = INT64_MAX;
        int64_t delay = INT64_MAX;
        uint64_t time = 0;
        bool used = false;
    };
    NTPPacket ntpBuffer[8];
    int bufferIndex = 0;
    uint64_t previousClockUpdate = 0;

    byte packetBuffer[NTP_PACKET_SIZE];
    EthernetUDP ntpSock;
    bool udpSetup = false;

    /* 
    Polling Interval is x where 2^x = Number of seconds between polls. According
    to NTP.org the minimum polling interval is 4 (16 seconds). Once the clock is
    considered synced then the default minimum polling interval is 6 (64s).
    NTP.org calculates estimated network load by assuming that clients are
    syncing with a polling interval of 7 (128s) so it may be wise to use 7
    instead of 6.
    */
    int pollingInterval = 1;
    long lastUpdate = 0;  // In ms
    unsigned int syncInterval = 1000; // In ms
    long lastSync = 0; // In ms
    long sentNTPPacket = 0; // In ms

    uint64_t currentEpoc = 0; // In us

    /*
    time.nist.gov and pool.ntp.org are "pools" of ntp servers. time.nist.gov
    servers are all stratum 1 time servers. Stratum 1 time server are accurate
    to 1 millisecond of the stratum 0 atmoic clocks. Ntp servers from
    pool.ntp.org can range between stratum 1 to stratum 4.
    */
    const char* ntpServers[3] = {"dailyserver", "time.nist.gov", "pool.ntp.org"};
    const char* ntpServer = ntpServers[0];
    IPAddress ntpIP;
    bool ipTranslated = false;

    Logging* logger;
    bool logging;

public:
    bool session = false;

    TimeClient();
    TimeClient(Logging* _logger);

    ~TimeClient();

    void setup();

    /**
     * This should be called in the main loop of your application. By default an
     * update from the NTP Server is only made every 60 seconds. This can be
     * configured in the TimeClient constructor.
     */
    void update();

    void startSession();
    void stopSession();

    uint32_t getDay();
    uint32_t getHours();
    uint32_t getMinutes();
    uint32_t getSeconds();

    /**
     * @return time formatted like `hh:mm:ss`
     */
    String getFormattedTime();

    /**
     * @return time in seconds since Jan. 1, 1970
     */
    uint64_t getEpochTime();
    
    /**
     * @return time in milliseconds since Jan. 1, 1970
     */
    uint64_t getEpochTimeMS();
    
    /**
     * Syncs currentEpoc to Teensy RTC's time every second. Returns currentEpoc
     * plus the time that has past since the last call to getTeensyTime minus 70
     * years to convert NTP time to system time.
     * 
     * @return time in microseconds since Jan. 1, 1970
     */
    uint64_t getEpochTimeUS();

private:

    void setPollingInterval();

    /**
     * Converts the NTP timestamp format to time in microseconds. NTP version 3
     * & 4 timestamp is split into two parts. The first 32 bits are seconds
     * since 1900 and the second 32 bits are the fraction of a second. Dividing
     * the 64 bit unsigned int by the maximum a 32 bit integer can hold should
     * get us the correct number of seconds since 1900. We then multiply this
     * number by the multiplier to get us the number of us/ms/s since 1900.
     */
    uint64_t timeFromNTPTimestamp(uint64_t timestamp);

    void makeNTPPacket(bool firstTime = false);
    void sendNTPPacket(bool firstTime = false);

    /**
     * The offset is calculated from the packet with the smallest delay out of
     * the last eight packets. This gets the index of the NTP packet with the
     * smallest delay.
     */
    int64_t getPeerUpdate();

    /**
     * Originate Timestamp (t1): time when ntp packet sent from client. 
     * Receive Timestamp (t2): time when ntp packet was received by server.
     * Transmit Timestamp (t3): time when ntp packet sent from the server.
     * Destination Timestamp (t4): time when ntp pack was received from server.
     * Reference Timestamp: time the clock on the server was last corrected. 
     *
     * offset = ((t2 - t1) + (t3 - t4)) / 2
     * delay = (t3 - t2) + (t4 - t1)
     * The offset is calculated from the packet with the smallest delay out of the
     * last eight packets
     */
    int64_t calculateOffset(bool firstTime = false);
    uint64_t readTimestamp(int start);
    void recvNTPPacket(bool firstTime = false);

    bool firstUpdate();
    bool tryNTPServer(int index);
    void getAddrInfo();

    void setTeensyTime(uint64_t newTime);
    uint32_t glitchlessRead(volatile uint32_t* ptr);
    uint64_t getTeensyTime();
};

#endif /* NTPCLIENT_H_ */