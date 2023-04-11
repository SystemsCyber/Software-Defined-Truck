#ifndef PTPClient_h
#define PTPClient_h

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

class PTPClient
{
private:
    uint8_t numSSSFs = 0;
    uint8_t index = 0;
    uint32_t syncCount = 0;
    uint32_t syncCountOffset = 0;
    uint64_t originate = 0ULL;
    uint64_t receive = 0ULL;

    int64_t t1 = 0LL;
    int64_t t2 = 0LL;
    int64_t t3 = 0LL;
    int64_t t4 = 0LL;

    struct PTPDataPoint
    {
        int64_t offset = INT64_MAX;
        int64_t delay = INT64_MAX;
        uint64_t time = 0;
        bool used = false;
    };
    PTPDataPoint buffer[8];
    uint8_t bufferIndex = 0;
    uint8_t indexSmallestDelay = 0;
    uint64_t previousClockUpdate = 0ULL;

    // uint32_t rtcSyncInterval = 1000000;
    // uint64_t lastRTCSync = 0ULL;
    // uint64_t currentEpoch = 0ULL;
    int64_t adjustment = 0LL;
    int64_t betweenRoundsOffset = 0LL; // Offset between Server Client rounds

    Logging *logger;
    bool logging;

public:
    uint64_t delayReqTimestamp = 0ULL;
    uint64_t transmit = 0ULL;

    PTPClient();
    PTPClient(Logging *logger);

    void start(uint8_t numMembers, uint8_t index);
    void stop();

    void syncUpdate(uint64_t us, uint64_t receiveUS);
    bool followUpUpdate(uint64_t us, uint64_t actualUS);
    
    void delayUpdate(uint64_t us);

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

    /**
     * The offset is calculated from the packet with the smallest delay out of
     * the last eight packets. This gets the index of the NTP packet with the
     * smallest delay.
     */
    int64_t getPeerUpdate();
    int64_t calculateOffset(uint64_t us);
    int64_t calculateOffsetDelay(uint64_t us);

    void setTeensyTime(uint64_t newTime);
    uint32_t glitchlessRead(volatile uint32_t* ptr);
    uint64_t getTeensyTime();
};
#endif // PTPClient_h