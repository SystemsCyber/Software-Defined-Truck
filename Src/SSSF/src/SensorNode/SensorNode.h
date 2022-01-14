#ifndef SensorNode_h_
#define SensorNode_h_

#include <Arduino.h>
#include <CANNode/CANNode.h>

class SensorNode: public virtual CANNode
{
public:
    uint8_t numSignals = 0;
    float *signals;

    struct WSensorBlock
    {
        uint8_t numSignals;
        float *signals;
    };

    SensorNode(): CANNode() {};
    virtual int read(struct WSensorBlock *buffer);
    virtual int write(struct WSensorBlock *sensorFrame);

    String dumpSensorBlock(struct WSensorBlock &senseBlock);
};

#endif /* SensorNode_h_ */