#include <Arduino.h>
#include <CANNode/CANNode.h>
#include <NetworkStats/NetworkStats.h>
#include <FlexCAN_T4.h>

NetworkStats::NetworkStats(uint16_t _index, size_t _size):
    index(_index), size(_size),
    Basics(new HealthBasics [_size]),
    HealthReport(new NodeReport [_size])
{}

NetworkStats::~NetworkStats()
{
    delete[] HealthReport;
    delete[] Basics;
}

void NetworkStats::update(uint16_t _index, int packetSize, uint32_t timestamp, uint32_t sequenceNumber)
{
    float now = float(millis());
    uint32_t seqNumOffset = sequenceNumber - Basics[_index].lastSequenceNumber;
    float ellapsedSeconds = (now - Basics[_index].lastMessageTime) / 1000;

    calculate(HealthReport[_index].latency, now - timestamp);
    calculate(HealthReport[_index].jitter, HealthReport[_index].latency.variance);
    HealthReport[_index].packetLoss = seqNumOffset - HealthReport[_index].latency.count;
    calculate(HealthReport[_index].goodput, (packetSize * 8) / ellapsedSeconds);
    
    Basics[_index].lastMessageTime = now;
    Basics[_index].lastSequenceNumber = sequenceNumber;
}

void NetworkStats::reset()
{
    for (size_t i = 0; i < size; i++)
    {
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