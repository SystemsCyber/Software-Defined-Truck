#include <Arduino.h>
#include <CANNode/CANNode.h>
#include <NetworkStats/NetworkStats.h>
#include <FlexCAN_T4.h>
#include <TimeClient/TimeClient.h>

NetworkStats::NetworkStats(size_t _size, TimeClient* _timeClient):
    timeClient(_timeClient),
    size(_size),
    Basics(new HealthBasics [_size]),
    HealthReport(new NodeReport [_size])
{}

NetworkStats::~NetworkStats()
{
    delete[] HealthReport;
    delete[] Basics;
}

void NetworkStats::update(uint16_t i, int packetSize, uint64_t timestamp, uint32_t sequenceNumber)
{
    int64_t _now = timeClient->getEpochTimeMS();
    int delay = _now - int64_t(timestamp);
    // Serial.print("Controller Send: ");
    // Serial.print(timestamp);
    // Serial.print(" SSSF Recv: ");
    // Serial.print(_now);
    // Serial.print(" Diff: ");
    // Serial.println(delay);
    float ellapsedSeconds = (_now - Basics[i].lastMessageTime) / 1000.0;

    calculate(HealthReport[i].latency, abs(delay));
    calculate(HealthReport[i].jitter, HealthReport[i].latency.variance);
    // If no packet loss then sequence number = last sequence number + 1
    int32_t packetsLost = int64_t(sequenceNumber) - (Basics[i].lastSequenceNumber + 1);
    // If packetsLost is negative then this usually indicates duplicate or
    // out of order frame. Etherway not a lost packet.
    HealthReport[i].packetLoss += (packetsLost > 0) ? packetsLost : 0;

    calculate(HealthReport[i].goodput, (packetSize * 8) / ellapsedSeconds);
    
    Basics[i].lastMessageTime = _now;
    Basics[i].lastSequenceNumber = int64_t(sequenceNumber);
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