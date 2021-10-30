#ifndef SensorNode_h_
#define SensorNode_h_

#include <Arduino.h>
#include <CANNode/CANNode.h>

class SensorNode: public virtual CANNode
{
public:
    struct CARLA_UDP: public Printable // CARLA frame information struct
    {
        uint32_t frameNumber;
        float throttle, steer, brake;
        bool handBrake, reverse, manualGearShift;
        uint8_t gear;

        size_t printTo(Print &p) const
        {
            size_t s = 0;
            s += p.printf("Frame: %d\n", frameNumber);
            s += p.printf("Throttle: %5f", throttle);
            s += p.printf("  Steer: %5f", steer);
            s += p.printf("  Brake: %5f\n", brake);
            s += p.printf("Reverse: %d", reverse);
            s += p.printf("  E-Brake: %d", handBrake);
            s += p.printf("  Manual: %d", manualGearShift);
            s += p.printf("  Gear: %d\n\n", gear);
            return s;
        };
    } _frame;

    struct WSensorBlock: public Printable
    {
        uint8_t numSignals;
        float *signals;

        size_t printTo(Print &p) const
        {
            size_t s = 0;
            for(uint8_t i = 0; i < numSignals; i++)
            {
                s += p.printf("%d: %3f ", i, (signals + i));
            }
            s += p.print("\n");
            return s;
        }
    };

    SensorNode(): CANNode() {};
    virtual int read(struct WSensorBlock *sensorFrame);
    virtual int write(struct WSensorBlock *sensorFrame);
};

#endif /* SensorNode_h_ */