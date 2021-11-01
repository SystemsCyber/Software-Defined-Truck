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
    for (size_t i = 0; i < size; i++)
    {
        if (members[i] == _id)
        {
            struct NodeReport &node = HealthReport[i];
            struct HealthBasics &basics = Basics[i];
            float now = float(millis());
            basics.count++;
            calculate(node.latency, basics.count, now - timestamp);
            calculate(node.jitter, basics.count, node.latency.variance);
            node.packetLoss = ((sequenceNumber - basics.count) / sequenceNumber) * 100;
            float ellapsedSeconds = (now - basics.lastMessageTime) / 1000;
            calculate(node.throughput, basics.count, (packetSize * 8) / ellapsedSeconds);
            basics.lastMessageTime = now;
        }
    }
}

void NetworkStats::reset()
{
    for (size_t i = 0; i < size; i++)
    {
        Basics[i].count = 0;
        Basics[i].lastMessageTime = millis();
        HealthReport[i] = {0};
    }
}

void NetworkStats::calculate(struct HealthCore &edge, uint32_t &count, float n)
{// From: https://en.wikipedia.org/wiki/Algorithms_for_calculating_variance#Welford's_online_algorithm
    edge.min = min(edge.min, n);
    edge.max = max(edge.max, n);
    delta = n - edge.mean;
    edge.mean += delta / count;
    delta2 = n - edge.mean;
    edge.M2 += delta * delta2;
    edge.variance = edge.M2 / count;
}