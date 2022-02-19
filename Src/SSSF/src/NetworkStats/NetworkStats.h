#ifndef network_stats_h_
#define network_stats_h_

#include <Arduino.h>
#include <CANNode/CANNode.h>
#include <limits>
#include <FlexCAN_T4.h>
#include <TimeClient/TimeClient.h>

class NetworkStats
{
private:
    float delta = 0;
    float delta2 = 0;
    TimeClient* timeClient;

public:
    struct HealthBasics
    {
        int64_t lastMessageTime = 0;
        uint32_t lastSequenceNumber = 0;
    };

    struct HealthCore
    {
        uint32_t count = 0;
        float min = std::numeric_limits<float>::max();
        float max = -std::numeric_limits<float>::max();
        float mean = 0.0;
        float variance = 0.0;
        float sumOfSquaredDifferences = 0.0;
    };

    struct NodeReport
    {
        float packetLoss = 0.0;
        struct HealthCore latency;
        struct HealthCore jitter;
        struct HealthCore goodput;
    };

    size_t size = 0;
    struct HealthBasics *Basics;
    struct NodeReport *HealthReport;

    NetworkStats(size_t _size, TimeClient* _timeClient);
    ~NetworkStats();
    void update(uint16_t _index, int packetSize, uint64_t timestamp, uint32_t sequenceNumber);
    void reset();
    // TODO: Reset every health report keep last seen sequence number

private:
    void calculate(struct HealthCore &edge, float n);
};

#endif /* network_stats_h_ */