#ifndef SensorNode_h_
#define SensorNode_h_

#include <Arduino.h>
#include <CANNode/CANNode.h>

class SensorNode: public CANNode
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
            p.printf("Frame: %d\n", frameNumber);
            p.printf("Throttle: %5f", throttle);
            p.printf("  Steer: %5f", steer);
            p.printf("  Brake: %5f\n", brake);
            p.printf("Reverse: %d", reverse);
            p.printf("  E-Brake: %d", handBrake);
            p.printf("  Manual: %d", manualGearShift);
            p.printf("  Gear: %d\n\n", gear);
        };
    } _frame;

    struct WSensorBlock: public Printable
    {
        uint8_t numSignals;
        float *signals;

        size_t printTo(Print &p) const
        {
            for(uint8_t i = 0; i < numSignals; i++)
            {
                p.printf("%d: %3f ", i, (signals + i));
            }
            p.print("\n");
        }
    };

    SensorNode(): CANNode() {};
    virtual int read(struct WSensorBlock *sensorFrame);
    virtual int write(struct WSensorBlock *sensorFrame);
};

#endif /* SensorNode_h_ */