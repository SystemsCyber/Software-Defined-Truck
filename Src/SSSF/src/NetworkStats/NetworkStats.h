#ifndef network_stats_h_
#define network_stats_h_

#include <Arduino.h>
#include <FlexCAN_T4.h>

class NetworkStats
{
private:
    uint16_t id;
    uint16_t *ids;
    size_t size = 0;

    uint32_t delta = 0;
    uint32_t delta2 = 0;

    struct AggregateFunctions
    {
        uint32_t count = 0;
        uint32_t min = (2^32) - 1;
        double mean = 0.0;
        uint32_t max = 0;
        uint32_t variance = 0;
        uint32_t M2 = 0;
    };

public:
    struct AggregateFunctions *latency;
    struct AggregateFunctions *jitter;
    struct AggregateFunctions *packetLoss;
    struct AggregateFunctions *throughput;

    NetworkStats(uint16_t _id, uint16_t *_ids, size_t _size) :
        id(_id), ids(_ids), size(_size),
        latency(new struct AggregateFunctions [_size]),
        jitter(new struct AggregateFunctions [_size]),
        packetLoss(new struct AggregateFunctions [_size]),
        throughput(new struct AggregateFunctions [_size])
        {};
    ~NetworkStats()
    {
        delete &latency;
        delete &jitter;
        delete &packetLoss;
        delete &throughput;
    };
    void update(CAN_message_t *msg);
    void reset();

private:
    void calculate(struct AggregateFunctions *m, uint32_t n);
};

#endif /* network_stats_h_ */