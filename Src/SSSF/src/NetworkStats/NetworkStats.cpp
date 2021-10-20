#include <Arduino.h>
#include <NetworkStats/NetworkStats.h>
#include <FlexCAN_T4.h>

void NetworkStats::update(CAN_message_t *msg)
{
    for (size_t i = 0; i < size; i++)
    {
        
    }
}

void NetworkStats::reset()
{
    delta = 0;
    delta2 = 0;

    for (size_t i = 0; i < size; i++)
    {
        memset(&latency[i], 0, sizeof(struct AggregateFunctions));
        memset(&jitter[i], 0, sizeof(struct AggregateFunctions));
        memset(&packetLoss[i], 0, sizeof(struct AggregateFunctions));
        memset(&throughput[i], 0, sizeof(struct AggregateFunctions));
    }
}

void NetworkStats::calculate(struct AggregateFunctions *edge, uint32_t n)
{// From: https://en.wikipedia.org/wiki/Algorithms_for_calculating_variance#Welford's_online_algorithm
    edge->min = (n < edge->min) ? n : edge->min;
    edge->max = (n > edge->max) ? n : edge->max;
    edge->count++;
    delta = n - edge->mean;
    edge->mean += delta / edge->count;
    delta2 = n - edge->mean;
    edge->M2 += delta * delta2;
    edge->variance = edge->M2 / edge->count;
}