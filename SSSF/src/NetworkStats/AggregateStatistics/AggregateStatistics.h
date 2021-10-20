#ifndef aggregate_statistics_h_
#define aggregate_statistics_h_

#include <Arduino.h>

class AggregateStatistics
{
private:
    uint32_t delta = 0;
    uint32_t delta2 = 0;
    uint32_t M2 = 0;

public:
    uint32_t count = 0;
    uint32_t min = (2^32) - 1;
    double mean = 0.0;
    uint32_t max = 0;
    uint32_t variance = 0;

    AggregateStatistics() = default;
    void update(uint32_t n)
    {// From: https://en.wikipedia.org/wiki/Algorithms_for_calculating_variance#Welford's_online_algorithm
        min = (n < min) ? n : min;
        max = (n > max) ? n : max;
        count++;
        delta = n - mean;
        mean += delta / count;
        delta2 = n - mean;
        M2 += delta * delta2;
        variance = M2 / count;
    };
    void reset()
    {
        delta = 0;
        delta2 = 0;
        M2 = 0;
        count = 0;
        min = (2^32) - 1;
        mean = 0.0;
        max = 0;
        variance = 0;
    };
};

#endif /* aggregate_statistics_h_ */