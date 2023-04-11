#ifndef SensorNode_h_
#define SensorNode_h_

#include <Arduino.h>
#include <CANNode/CANNode.h>

class SensorNode: public virtual CANNode
{
public:
    uint8_t numSignals = 0;
    float signals[16] = {0.0};

    struct WSensorBlock
    {
        uint8_t numSignals;
        float *signals;
    };

    SensorNode(): CANNode() {};
    int unpackSensorBlock(struct WSensorBlock &signals, uint8_t *msgBuffer);
    int packSensorBlock(struct WSensorBlock &signals, uint8_t *msgBuffer);

    String dumpSensorBlock(struct WSensorBlock &senseBlock);
};

#endif /* SensorNode_h_ */