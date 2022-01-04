#include <Arduino.h>
#include <CANNode/CANNode.h>
#include <NetworkStats/NetworkStats.h>
#include <FlexCAN_T4.h>

NetworkStats::NetworkStats(uint16_t _id, uint16_t *_members, size_t _size):
    id(_id), members(_members), size(_size),
    Basics(new HealthBasics [_size]),
    HealthReport(new NodeReport [_size])
{}

NetworkStats::~NetworkStats()
{
    delete &HealthReport;
    delete &Basics;
}

void NetworkStats::update(uint16_t _id, int packetSize, uint32_t timestamp, uint32_t sequenceNumber)
{
    float now = float(millis());
    uint32_t seqNumOffset = sequenceNumber - Basics[_id].lastSequenceNumber;
    float ellapsedSeconds = (now - Basics[_id].lastMessageTime) / 1000;

    calculate(HealthReport[_id].latency, now - timestamp);
    calculate(HealthReport[_id].jitter, HealthReport[_id].latency.variance);
    HealthReport[_id].packetLoss = seqNumOffset - HealthReport[_id].latency.count;
    calculate(HealthReport[_id].goodput, (packetSize * 8) / ellapsedSeconds);
    
    Basics[_id].lastMessageTime = now;
    Basics[_id].lastSequenceNumber = sequenceNumber;
}

void NetworkStats::reset()
{
    for (size_t i = 0; i < size; i++)
    {
        Basics[i].lastSequenceNumber = 0; //Not sure if this is right...
        Basics[i].lastMessageTime = millis();
        HealthReport[i] = {0};
    }
}

void NetworkStats::calculate(struct HealthCore &edge, float n)
{// From: https://en.wikipedia.org/wiki/Algorithms_for_calculating_variance#Welford's_online_algorithm
    edge.min = min(edge.min, n);
    edge.max = max(edge.max, n);
    edge.count++;
    delta = n - edge.mean;
    edge.mean += delta / edge.count;
    delta2 = n - edge.mean;
    edge.sumOfSquaredDifferences += delta * delta2;
    edge.variance = edge.sumOfSquaredDifferences / edge.count;
}