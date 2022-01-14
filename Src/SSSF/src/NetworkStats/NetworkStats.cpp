#include <Arduino.h>
#include <CANNode/CANNode.h>
#include <NetworkStats/NetworkStats.h>
#include <FlexCAN_T4.h>

NetworkStats::NetworkStats(size_t _size):
    size(_size),
    Basics(new HealthBasics [_size]),
    HealthReport(new NodeReport [_size])
{}

NetworkStats::~NetworkStats()
{
    delete[] HealthReport;
    delete[] Basics;
}

void NetworkStats::update(uint16_t i, int packetSize, uint32_t timestamp, uint32_t sequenceNumber)
{
    float now = float(millis());
    uint32_t seqNumOffset = sequenceNumber - Basics[i].lastSequenceNumber;
    float ellapsedSeconds = (now - Basics[i].lastMessageTime) / 1000;

    calculate(HealthReport[i].latency, now - timestamp);
    calculate(HealthReport[i].jitter, HealthReport[i].latency.variance);
    HealthReport[i].packetLoss = seqNumOffset - HealthReport[i].latency.count;
    calculate(HealthReport[i].goodput, (packetSize * 8) / ellapsedSeconds);
    
    Basics[i].lastMessageTime = now;
    Basics[i].lastSequenceNumber = sequenceNumber;
}

void NetworkStats::reset()
{
    delete[] HealthReport;
    HealthReport = new NodeReport[size];
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